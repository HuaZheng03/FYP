package org.onosproject.pathloadbalancer;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.felix.scr.annotations.*;
import org.onlab.packet.*;
import org.onosproject.core.ApplicationId;
import org.onosproject.core.CoreService;
import org.onosproject.net.*;
import org.onosproject.net.flow.*;
import org.onosproject.net.host.HostService;
import org.onosproject.net.packet.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.File;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.nio.file.attribute.FileTime;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

@Component(immediate = true)
public class PathLoadBalancerApp {

    private static final Logger log = LoggerFactory.getLogger(PathLoadBalancerApp.class);

    private static final int FLOW_PRIORITY = 40000;
    private static final int IDLE_TIMEOUT_SECONDS = 300;

    // Update to your actual JSON path
    private static final String WEIGHTS_FILE_PATH =
            "/root/onos/apache-karaf-4.2.9/data/onos_path_selection.json";
    private static final int FILE_CHECK_INTERVAL_SEC = 5;

    @Reference(cardinality = ReferenceCardinality.MANDATORY_UNARY)
    protected CoreService coreService;
    @Reference(cardinality = ReferenceCardinality.MANDATORY_UNARY)
    protected PacketService packetService;
    @Reference(cardinality = ReferenceCardinality.MANDATORY_UNARY)
    protected FlowRuleService flowRuleService;
    @Reference(cardinality = ReferenceCardinality.MANDATORY_UNARY)
    protected HostService hostService;

    private ApplicationId appId;
    private final InternalPacketProcessor processor = new InternalPacketProcessor();

    // Route weights: "leaf6->leaf1" -> {0:0.4, 1:0.6}
    private final Map<String, Map<Integer, Double>> pathRatios = new ConcurrentHashMap<>();

    // Smooth-WRR state: "leaf6->leaf1" -> {0:cw0, 1:cw1}
    private final Map<String, Map<Integer, Integer>> smoothWrrState = new ConcurrentHashMap<>();

    private final ObjectMapper mapper = new ObjectMapper();
    private ScheduledExecutorService fileMonitor;
    private volatile FileTime lastModifiedTime;

    // Flow stickiness: keep same spine for same 5-tuple while rule lives.
    // Key includes direction (srcIP->dstIP etc) so forward and reverse are distinct;
    // but we install both directions immediately with SAME spine.
    private final Map<FlowKey, Integer> flowToSpine = new ConcurrentHashMap<>();

    @Activate
    protected void activate() {
        appId = coreService.registerApplication("org.onosproject.pathloadbalancer");
        initDefaultWeights();

        packetService.addProcessor(processor, PacketProcessor.director(2));

        // Request IPv4 only; ARP is left to ProxyARP (no ARP requestPackets here).
        TrafficSelector selector = DefaultTrafficSelector.builder()
                .matchEthType(Ethernet.TYPE_IPV4)
                .build();
        packetService.requestPackets(selector, PacketPriority.REACTIVE, appId);

        startFileMonitor();

        log.info("PathLoadBalancer started (no-flood, leaf+spine programming).");
    }

    @Deactivate
    protected void deactivate() {
        if (fileMonitor != null) {
            fileMonitor.shutdownNow();
        }

        TrafficSelector selector = DefaultTrafficSelector.builder()
                .matchEthType(Ethernet.TYPE_IPV4)
                .build();
        packetService.cancelPackets(selector, PacketPriority.REACTIVE, appId);

        packetService.removeProcessor(processor);
        flowRuleService.removeFlowRulesById(appId);

        flowToSpine.clear();
        log.info("PathLoadBalancer stopped.");
    }

    // ------------------------- Packet processing -------------------------

    private class InternalPacketProcessor implements PacketProcessor {
        @Override
        public void process(PacketContext context) {
            if (context.isHandled()) {
                return;
            }

            Ethernet eth = context.inPacket().parsed();
            if (eth == null) {
                return;
            }

            if (eth.getEtherType() != Ethernet.TYPE_IPV4) {
                return;
            }

            // Ignore multicast/broadcast IPv4 here to avoid fabric floods.
            MacAddress dstMac = eth.getDestinationMAC();
            if (dstMac.isMulticast() || dstMac.isBroadcast()) {
                context.block();
                return;
            }

            Host srcHost = getHostByMac(eth.getSourceMAC());
            Host dstHost = getHostByMac(dstMac);
            if (srcHost == null || dstHost == null) {
                // If host is unknown, do NOT flood; let ProxyARP/host discovery learn.
                context.block();
                return;
            }

            DeviceId srcLeaf = srcHost.location().deviceId();
            DeviceId dstLeaf = dstHost.location().deviceId();

            // If same leaf, just output to destination host port on that leaf.
            if (srcLeaf.equals(dstLeaf)) {
                packetOut(context, dstHost.location().port());
                return;
            }

            IPv4 ipv4 = (IPv4) eth.getPayload();
            FlowKey fk = FlowKey.from(ipv4);

            String srcName = leafName(srcLeaf);
            String dstName = leafName(dstLeaf);
            String routeKey = srcName + "->" + dstName;

            int spineChoice = flowToSpine.computeIfAbsent(fk, k -> selectPathSmoothWrr(routeKey));

            // Program both directions end-to-end using SAME spineChoice.
            boolean ok = installBidirectionalPath(srcHost, dstHost, fk, spineChoice);
            if (!ok) {
                context.block();
                return;
            }

            // Send this first packet along chosen path (no FLOOD).
            PortNumber outPort = uplinkPort(srcLeaf, spineChoice);
            if (outPort == null) {
                context.block();
                return;
            }
            packetOut(context, outPort);
        }
    }

    private void packetOut(PacketContext context, PortNumber portNumber) {
        context.treatmentBuilder().setOutput(portNumber);
        context.send();
    }

    private Host getHostByMac(MacAddress mac) {
        Set<Host> hs = hostService.getHostsByMac(mac);
        if (hs == null || hs.isEmpty()) {
            return null;
        }
        return hs.iterator().next();
    }

    // ------------------------- Flow installation -------------------------

    private boolean installBidirectionalPath(Host a, Host b, FlowKey fk, int spineChoice) {
        DeviceId leafA = a.location().deviceId();
        DeviceId leafB = b.location().deviceId();

        DeviceId spine = (spineChoice == 0)
                ? DeviceId.deviceId("of:0000d6dee87ca841")   // spine1
                : DeviceId.deviceId("of:00000ac352fff34c");  // spine2

        PortNumber aToSpine = uplinkPort(leafA, spineChoice);
        PortNumber spineToB = downlinkPort(spine, leafB);
        PortNumber bHostPort = b.location().port();

        PortNumber bToSpine = uplinkPort(leafB, spineChoice);
        PortNumber spineToA = downlinkPort(spine, leafA);
        PortNumber aHostPort = a.location().port();

        if (aToSpine == null || bToSpine == null || spineToA == null || spineToB == null) {
            log.warn("Missing port mapping for leaf/spine. aToSpine={}, spineToB={}, bToSpine={}, spineToA={}",
                    aToSpine, spineToB, bToSpine, spineToA);
            return false;
        }

        // Forward: A -> B (leafA -> spine -> leafB -> host)
        installFlow(leafA, fk.selectorForward(), aToSpine);
        installFlow(spine, fk.selectorForward(), spineToB);
        installFlow(leafB, fk.selectorForward(), bHostPort);

        // Reverse: B -> A (same spine) — selectorReverse swaps tuple.
        installFlow(leafB, fk.selectorReverse(), bToSpine);
        installFlow(spine, fk.selectorReverse(), spineToA);
        installFlow(leafA, fk.selectorReverse(), aHostPort);

        return true;
    }

    private void installFlow(DeviceId deviceId, TrafficSelector selector, PortNumber outPort) {
        TrafficTreatment treatment = DefaultTrafficTreatment.builder()
                .setOutput(outPort)
                .build();

        FlowRule rule = DefaultFlowRule.builder()
                .forDevice(deviceId)
                .fromApp(appId)
                .withPriority(FLOW_PRIORITY)
                .withSelector(selector)
                .withTreatment(treatment)
                .makeTemporary(IDLE_TIMEOUT_SECONDS)
                .build();

        flowRuleService.applyFlowRules(rule);
    }

    // ------------------------- Flow key + selectors -------------------------

    private static final class FlowKey {
        final IpAddress srcIp;
        final IpAddress dstIp;
        final byte proto;
        final int srcPortOrType;
        final int dstPortOrCode;

        private FlowKey(IpAddress srcIp, IpAddress dstIp, byte proto, int sp, int dp) {
            this.srcIp = srcIp;
            this.dstIp = dstIp;
            this.proto = proto;
            this.srcPortOrType = sp;
            this.dstPortOrCode = dp;
        }

        static FlowKey from(IPv4 ipv4) {
            IpAddress src = IpAddress.valueOf(ipv4.getSourceAddress());
            IpAddress dst = IpAddress.valueOf(ipv4.getDestinationAddress());
            byte p = ipv4.getProtocol();
            int sp = 0, dp = 0;

            if (p == IPv4.PROTOCOL_TCP) {
                TCP tcp = (TCP) ipv4.getPayload();
                sp = tcp.getSourcePort();
                dp = tcp.getDestinationPort();
            } else if (p == IPv4.PROTOCOL_UDP) {
                UDP udp = (UDP) ipv4.getPayload();
                sp = udp.getSourcePort();
                dp = udp.getDestinationPort();
            } else if (p == IPv4.PROTOCOL_ICMP) {
                ICMP icmp = (ICMP) ipv4.getPayload();
                sp = icmp.getIcmpType();
                dp = icmp.getIcmpCode();
            }
            return new FlowKey(src, dst, p, sp, dp);
        }

        TrafficSelector selectorForward() {
            return buildSelector(srcIp, dstIp, proto, srcPortOrType, dstPortOrCode);
        }

        TrafficSelector selectorReverse() {
            return buildSelector(dstIp, srcIp, proto, dstPortOrCode, srcPortOrType);
        }

        private static TrafficSelector buildSelector(IpAddress src, IpAddress dst, byte p, int sp, int dp) {
            TrafficSelector.Builder sb = DefaultTrafficSelector.builder()
                    .matchEthType(Ethernet.TYPE_IPV4)
                    .matchIPSrc(IpPrefix.valueOf(src, 32))
                    .matchIPDst(IpPrefix.valueOf(dst, 32))
                    .matchIPProtocol(p);

            if (p == IPv4.PROTOCOL_TCP) {
                sb.matchTcpSrc(TpPort.tpPort(sp)).matchTcpDst(TpPort.tpPort(dp));
            } else if (p == IPv4.PROTOCOL_UDP) {
                sb.matchUdpSrc(TpPort.tpPort(sp)).matchUdpDst(TpPort.tpPort(dp));
            } else if (p == IPv4.PROTOCOL_ICMP) {
                sb.matchIcmpType((byte) sp).matchIcmpCode((byte) dp);
            }
            return sb.build();
        }

        @Override
        public int hashCode() {
            return Objects.hash(srcIp, dstIp, proto, srcPortOrType, dstPortOrCode);
        }

        @Override
        public boolean equals(Object o) {
            if (!(o instanceof FlowKey)) return false;
            FlowKey other = (FlowKey) o;
            return Objects.equals(srcIp, other.srcIp)
                    && Objects.equals(dstIp, other.dstIp)
                    && proto == other.proto
                    && srcPortOrType == other.srcPortOrType
                    && dstPortOrCode == other.dstPortOrCode;
        }
    }

    // ------------------------- Path selection -------------------------

    private synchronized int selectPathSmoothWrr(String routeKey) {
        Map<Integer, Double> ratios = pathRatios.get(routeKey);
        if (ratios == null) {
            ratios = Map.of(0, 0.5, 1, 0.5);
        }

        double w0 = ratios.getOrDefault(0, 0.5);
        double w1 = ratios.getOrDefault(1, 0.5);
        double sum = w0 + w1;
        if (sum <= 0) {
            w0 = 0.5; w1 = 0.5; sum = 1.0;
        }

        int ew0 = (int) Math.round((w0 / sum) * 100);
        int ew1 = (int) Math.round((w1 / sum) * 100);
        int total = ew0 + ew1;

        Map<Integer, Integer> st = smoothWrrState.computeIfAbsent(routeKey, k -> new ConcurrentHashMap<>());
        int cw0 = st.getOrDefault(0, 0) + ew0;
        int cw1 = st.getOrDefault(1, 0) + ew1;

        int selected;
        if (cw0 > cw1) {
            selected = 0;
            cw0 -= total;
        } else {
            selected = 1;
            cw1 -= total;
        }

        st.put(0, cw0);
        st.put(1, cw1);
        return selected;
    }

    // ------------------------- Port mapping (leaf<->spine) -------------------------

    // leaf uplinks: path0=spine1, path1=spine2
    private PortNumber uplinkPort(DeviceId leaf, int spineChoice) {
        String dpid = leaf.toString();
        boolean toSpine1 = (spineChoice == 0);

        // leaf1: spine1=1, spine2=5
        if (dpid.endsWith("72ecfb3ccb4c")) return PortNumber.portNumber(toSpine1 ? 1 : 5);
        // leaf2: spine1=3, spine2=1
        if (dpid.endsWith("42b1a1405d41")) return PortNumber.portNumber(toSpine1 ? 3 : 1);
        // leaf3: spine1=1, spine2=2
        if (dpid.endsWith("32095cbf1043")) return PortNumber.portNumber(toSpine1 ? 1 : 2);
        // leaf6: spine1=1, spine2=2
        if (dpid.endsWith("ca44716bdf4b")) return PortNumber.portNumber(toSpine1 ? 1 : 2);

        return null;
    }

    // spine downlinks to leaves
    private PortNumber downlinkPort(DeviceId spine, DeviceId leaf) {
        String s = spine.toString();
        String l = leaf.toString();

        // spine1 ports: leaf1=1 leaf6=2 leaf2=3 leaf3=4
        if (s.endsWith("d6dee87ca841")) {
            if (l.endsWith("72ecfb3ccb4c")) return PortNumber.portNumber(1);
            if (l.endsWith("ca44716bdf4b")) return PortNumber.portNumber(2);
            if (l.endsWith("42b1a1405d41")) return PortNumber.portNumber(3);
            if (l.endsWith("32095cbf1043")) return PortNumber.portNumber(4);
        }

        // spine2 ports: leaf1=1 leaf2=2 leaf3=3 leaf6=4
        if (s.endsWith("0ac352fff34c")) {
            if (l.endsWith("72ecfb3ccb4c")) return PortNumber.portNumber(1);
            if (l.endsWith("42b1a1405d41")) return PortNumber.portNumber(2);
            if (l.endsWith("32095cbf1043")) return PortNumber.portNumber(3);
            if (l.endsWith("ca44716bdf4b")) return PortNumber.portNumber(4);
        }

        return null;
    }

    private String leafName(DeviceId leaf) {
        String dpid = leaf.toString();
        if (dpid.endsWith("72ecfb3ccb4c")) return "leaf1";
        if (dpid.endsWith("42b1a1405d41")) return "leaf2";
        if (dpid.endsWith("32095cbf1043")) return "leaf3";
        if (dpid.endsWith("ca44716bdf4b")) return "leaf6";
        return dpid;
    }

    // ------------------------- Weights file monitor -------------------------

    private void initDefaultWeights() {
        // Initialize all ordered leaf pairs in your topology.
        String[] leaves = {"leaf1", "leaf2", "leaf3", "leaf6"};
        for (String a : leaves) {
            for (String b : leaves) {
                if (!a.equals(b)) {
                    pathRatios.put(a + "->" + b, new ConcurrentHashMap<>(Map.of(0, 0.5, 1, 0.5)));
                    smoothWrrState.put(a + "->" + b, new ConcurrentHashMap<>(Map.of(0, 0, 1, 0)));
                }
            }
        }
    }

    private void startFileMonitor() {
        fileMonitor = Executors.newSingleThreadScheduledExecutor();
        fileMonitor.scheduleAtFixedRate(() -> {
            try {
                checkAndReloadWeights();
            } catch (Exception e) {
                log.warn("Weights reload error: {}", e.getMessage());
            }
        }, FILE_CHECK_INTERVAL_SEC, FILE_CHECK_INTERVAL_SEC, TimeUnit.SECONDS);
    }

    private void checkAndReloadWeights() throws Exception {
        File f = new File(WEIGHTS_FILE_PATH);
        if (!f.exists()) {
            return;
        }
        FileTime mt = Files.getLastModifiedTime(Paths.get(WEIGHTS_FILE_PATH));
        if (lastModifiedTime != null && mt.compareTo(lastModifiedTime) <= 0) {
            return;
        }
        lastModifiedTime = mt;
        loadWeightsFromFile();
    }

    // Supports your newer JSON structure:
    // root.path_selection_weights.<route>.path_details.path_0.selection_ratio
    private void loadWeightsFromFile() throws Exception {
        String content = Files.readString(Paths.get(WEIGHTS_FILE_PATH));
        JsonNode root = mapper.readTree(content);
        JsonNode weightsNode = root.get("path_selection_weights");
        if (weightsNode == null) {
            return;
        }

        Iterator<Map.Entry<String, JsonNode>> it = weightsNode.fields();
        while (it.hasNext()) {
            Map.Entry<String, JsonNode> e = it.next();
            String routeKey = e.getKey();
            JsonNode pathDetails = e.getValue().get("path_details");
            if (pathDetails == null) {
                continue;
            }

            JsonNode p0 = pathDetails.get("path_0");
            JsonNode p1 = pathDetails.get("path_1");
            if (p0 == null || p1 == null) {
                continue;
            }

            double r0 = p0.has("selection_ratio") ? p0.get("selection_ratio").asDouble() : 0.5;
            double r1 = p1.has("selection_ratio") ? p1.get("selection_ratio").asDouble() : 0.5;

            pathRatios.put(routeKey, new ConcurrentHashMap<>(Map.of(0, r0, 1, r1)));

            // Reset WRR accumulator so new distribution takes effect cleanly for new flows
            smoothWrrState.put(routeKey, new ConcurrentHashMap<>(Map.of(0, 0, 1, 0)));
        }

        log.info("Weights reloaded from {}", WEIGHTS_FILE_PATH);
    }
}
