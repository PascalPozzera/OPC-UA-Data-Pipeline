import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from asyncua import ua, Server, Node
from asyncua.common.methods import uamethod

APP_NAME = "PickAndPlace OPC UA Server"
ENDPOINT = "opc.tcp://0.0.0.0:4840/pnp/"
NAMESPACE_URI = "urn:example:pick-and-place"


class DeviationTracker:
    """
    Tracks deviations between target and actual values.
    Triggers alarms based on two rules:
    1. Immediate alarm if deviation > 10% in a single cycle
    2. Trend alarm if deviation > 2% for 3 consecutive cycles
    """
    def __init__(self, percent2_threshold=2.0, percent10_threshold=10.0):
        self.t2 = percent2_threshold
        self.t10 = percent10_threshold
        self.history: Dict[str, List[float]] = {}  # Stores last 3 deviation values per metric

    def record(self, name: str, target: float, actual: float) -> Tuple[bool, str, List[float]]:
        """Records a value and checks for deviation alarms. Returns (alarm_triggered, message, history)."""
        if target == 0:
            return False, "", []
        pct = (actual - target) / target * 100.0
        buf = self.history.setdefault(name, [])
        buf.append(pct)
        if len(buf) > 3:
            buf.pop(0)
        if abs(pct) > self.t10:
            return True, f"{name}: Abweichung {pct:.2f}% (>10%)", buf.copy()
        if len(buf) == 3 and all(abs(v) > self.t2 for v in buf):
            tr = ", ".join(f"{v:.2f}%" for v in buf)
            return True, f"{name}: 3x in Folge Abweichung >2% ({tr})", buf.copy()
        return False, "", buf.copy()


class MachineModel:
    """Data model representing the Pick-and-Place machine state and parameters."""
    def __init__(self):
        # Machine states: Running, Stopped, Error, Maintenance, Setup
        self.status = "Running"
        self.current_operation = "Loading PCB"


        self.machine_name = "ChipPlace Lightning #4"
        self.machine_serial = "CPL4000-2023-004"
        self.plant = "Dresden Electronics Manufacturing"
        self.production_segment = "Automotive Electronics"
        self.production_line = "SMT Assembly Line 5"


        import uuid
        new_suffix = uuid.uuid4().hex[:4].upper()
        self.production_order = f"PO-2024-ECU-{new_suffix}"
        self.article = "ART-ECU-V2-MAIN"
        self.quantity_pcbs = 8000 


        self.target_placement_rate_cph = 42000.0
        self.actual_placement_rate_cph = 41847.0
        self.target_accuracy_x_um = 15.0
        self.actual_accuracy_x_um = 12.3
        self.target_accuracy_y_um = 15.0
        self.actual_accuracy_y_um = 13.7
        self.vision_processing_time_ms = 28.5
        self.head_pos_x_mm = 147.823
        self.head_pos_y_mm = 89.456
        self.target_head_accel_g = 2.8
        self.actual_head_accel_g = 2.75
        self.vacuum_pressure_kpa = -78.5
        self.target_cycle_time_s = 0.72
        self.actual_cycle_time_s = 0.73
        self.current_nozzle_type = 4
        self.vision_pass_rate_pct = 99.7


        self.feeder_counts: Dict[int, int] = {1: 4847, 2: 12456, 3: 8923, 4: 156}


        self.pcb_index_current = 2847
        self.components_good = 12847569
        self.components_failed_pickup = 2847
        self.components_failed_vision = 1923
        self.components_failed_placement = 1156
        self.total_components_failed = 5926
        self.total_components = 12853495
        self.total_components = 12853495
        self.pcbs_completed_good = 0
        self.pcbs_completed_bad = 0
        import random
        self.total_pcbs_order = random.randint(1000, 5000)
        self.quantity_pcbs = self.total_pcbs_order
        self.production_order_progress_pct = 0.0
        self.nozzle_change_count = 847
        self.component_traceability_lot = "COMP-LOT-2024-R456"
        self.spc_placement_offset_trend = "+2.3 μm drift"


        self._dev = DeviationTracker()

    def tick(self):
        if self.status == "Running":
            self.actual_placement_rate_cph = max(0.0, self.actual_placement_rate_cph + 5.0)
        alarm, text, _ = self._dev.record(
            "PlacementRate", self.target_placement_rate_cph, self.actual_placement_rate_cph
        )
        return alarm, text


class PickAndPlaceServer:
    """OPC-UA Server simulating a Pick-and-Place SMT machine with realistic behavior."""
    def __init__(self):
        self.server: Optional[Server] = None
        self.idx: int = 0
        self.root_obj: Optional[Node] = None
        self.model = MachineModel()

        # Kernknoten
        self.status_node: Optional[Node] = None
        self.operation_node: Optional[Node] = None
        self.alarm_list_node: Optional[Node] = None
        self.nodes: Dict[str, Node] = {}
        self._last_push: bool = False
        self._feeder_low_state = {1: False, 2: False, 3: False, 4: False}
        self._feeder_empty_state = {1: False, 2: False, 3: False, 4: False}
        self._pending_alarms: List[Tuple[str, bool]] = []

    async def _add(self, name: str, value, vtype: ua.VariantType) -> Node:
        node_id = ua.NodeId(name, self.idx)
        node = await self.root_obj.add_variable(node_id, name, value, varianttype=vtype)
        await node.set_writable()
        self.nodes[name] = node
        return node

    async def init(self):
        self.server = Server()
        await self.server.init()
        self.server.set_endpoint(ENDPOINT)
        self.server.set_server_name(APP_NAME)
        self.idx = await self.server.register_namespace(NAMESPACE_URI)
        self.server.set_security_policy([ua.SecurityPolicyType.NoSecurity])

        objects = self.server.nodes.objects
        self.root_obj = await objects.add_object(ua.NodeId("PickAndPlace", self.idx), "PickAndPlace")

        self.status_node = await self._add("Status", self.model.status, ua.VariantType.String)
        self.operation_node = await self._add("CurrentOperation", self.model.current_operation, ua.VariantType.String)

        await self.root_obj.add_method(ua.NodeId("SimulateError", self.idx), "SimulateError", self.simulate_error, [], [])

        await self._add("MachineName", self.model.machine_name, ua.VariantType.String)
        await self._add("MachineSerialNumber", self.model.machine_serial, ua.VariantType.String)
        await self._add("Plant", self.model.plant, ua.VariantType.String)
        await self._add("ProductionSegment", self.model.production_segment, ua.VariantType.String)
        await self._add("ProductionLine", self.model.production_line, ua.VariantType.String)

        await self._add("ProductionOrder", self.model.production_order, ua.VariantType.String)
        await self._add("Article", self.model.article, ua.VariantType.String)
        await self._add("QuantityPCBs", self.model.quantity_pcbs, ua.VariantType.UInt32)

        await self._add("TargetPlacementRateCPH", self.model.target_placement_rate_cph, ua.VariantType.Double)
        await self._add("ActualPlacementRateCPH", self.model.actual_placement_rate_cph, ua.VariantType.Double)
        await self._add("TargetAccuracyXum", self.model.target_accuracy_x_um, ua.VariantType.Double)
        await self._add("ActualAccuracyXum", self.model.actual_accuracy_x_um, ua.VariantType.Double)
        await self._add("TargetAccuracyYum", self.model.target_accuracy_y_um, ua.VariantType.Double)
        await self._add("ActualAccuracyYum", self.model.actual_accuracy_y_um, ua.VariantType.Double)
        await self._add("VisionProcessingTimeMs", self.model.vision_processing_time_ms, ua.VariantType.Double)
        await self._add("HeadPosXmm", self.model.head_pos_x_mm, ua.VariantType.Double)
        await self._add("HeadPosYmm", self.model.head_pos_y_mm, ua.VariantType.Double)
        await self._add("TargetHeadAccelG", self.model.target_head_accel_g, ua.VariantType.Double)
        await self._add("ActualHeadAccelG", self.model.actual_head_accel_g, ua.VariantType.Double)
        await self._add("VacuumPressureKPa", self.model.vacuum_pressure_kpa, ua.VariantType.Double)
        await self._add("TargetCycleTimeS", self.model.target_cycle_time_s, ua.VariantType.Double)
        await self._add("ActualCycleTimeS", self.model.actual_cycle_time_s, ua.VariantType.Double)
        await self._add("CurrentNozzleType", self.model.current_nozzle_type, ua.VariantType.UInt16)
        await self._add("VisionPassRatePct", self.model.vision_pass_rate_pct, ua.VariantType.Double)

        for i in range(1, 5):
            await self._add(f"Feeder{i:02d}Count", self.model.feeder_counts.get(i, 0), ua.VariantType.UInt32)

        await self._add("PCBIndexCurrent", self.model.pcb_index_current, ua.VariantType.UInt32)
        await self._add("ComponentsPlacedGood", self.model.components_good, ua.VariantType.UInt64)
        await self._add("ComponentsFailedPickup", self.model.components_failed_pickup, ua.VariantType.UInt64)
        await self._add("ComponentsFailedVision", self.model.components_failed_vision, ua.VariantType.UInt64)
        await self._add("ComponentsFailedPlacement", self.model.components_failed_placement, ua.VariantType.UInt64)
        await self._add("TotalComponentsFailed", self.model.total_components_failed, ua.VariantType.UInt64)
        await self._add("TotalComponents", self.model.total_components, ua.VariantType.UInt64)
        await self._add("PCBsCompletedGood", self.model.pcbs_completed_good, ua.VariantType.UInt32)
        await self._add("PCBsCompletedBad", self.model.pcbs_completed_bad, ua.VariantType.UInt32)
        await self._add("TotalPCBsOrder", self.model.total_pcbs_order, ua.VariantType.UInt32)
        await self._add("ProductionOrderProgressPct", self.model.production_order_progress_pct, ua.VariantType.Double)
        await self._add("NozzleChangeCount", self.model.nozzle_change_count, ua.VariantType.UInt32)
        await self._add("ComponentTraceabilityLot", self.model.component_traceability_lot, ua.VariantType.String)
        await self._add("SPCPlacementOffsetTrend", self.model.spc_placement_offset_trend, ua.VariantType.String)

        self.alarm_list_node = await self._add("ActiveAlarms", "", ua.VariantType.String)
        self.current_error_node = await self._add("CurrentError", "", ua.VariantType.String)

        await self.root_obj.add_method(ua.NodeId("StartMachine", self.idx), "StartMachine", self.start_machine, [], [])
        await self.root_obj.add_method(ua.NodeId("StopMachine", self.idx), "StopMachine", self.stop_machine, [], [])
        await self.root_obj.add_method(ua.NodeId("EnterMaintenance", self.idx), "EnterMaintenance", self.enter_maintenance, [], [])
        await self.root_obj.add_method(ua.NodeId("EnterSetup", self.idx), "EnterSetup", self.enter_setup, [], [])
        await self.root_obj.add_method(ua.NodeId("EmergencyStop", self.idx), "EmergencyStop", self.emergency_stop, [], [])
        await self.root_obj.add_method(ua.NodeId("AcknowledgeAlarms", self.idx), "AcknowledgeAlarms", self.acknowledge_alarms, [], [])

    @uamethod
    async def start_machine(self, _parent):
        self._pending_alarms.clear()
        await self.current_error_node.write_value(ua.Variant("", ua.VariantType.String))
        await self.alarm_list_node.write_value(ua.Variant("", ua.VariantType.String))
        
        await self.status_node.write_value("Starting")
        await asyncio.sleep(0.5)
        await self.status_node.write_value("Running")
        self.model.status = "Running"

    @uamethod
    async def stop_machine(self, _parent):
        await self.status_node.write_value("Stopping")
        await asyncio.sleep(0.5)
        await self.status_node.write_value("Stopped")
        self.model.status = "Stopped"

    @uamethod
    async def enter_maintenance(self, _parent):
        await self.status_node.write_value("Maintenance")
        self.model.status = "Maintenance"

    @uamethod
    async def enter_setup(self, _parent):
        await self.status_node.write_value("Setup")
        self.model.status = "Setup"

    @uamethod
    async def emergency_stop(self, _parent):
        await self.status_node.write_value("Error")
        self.model.status = "Error"

    @uamethod
    async def acknowledge_alarms(self, _parent):
        self._pending_alarms.clear()
        await self.current_error_node.write_value(ua.Variant("", ua.VariantType.String))
        await self.alarm_list_node.write_value(ua.Variant("", ua.VariantType.String))
        
        await self.status_node.write_value(ua.Variant("Running", ua.VariantType.String))
        self.model.status = "Running"

    async def run(self):
        assert self.server is not None
        async with self.server:
            # Server Loop
            while True:
                await asyncio.sleep(1.0)
                await self._cycle()

    async def _cycle(self):
        current_status_val = await self.status_node.read_value()
        self.model.status = current_status_val

        if self.model.status == "Running":
            import random
            
            # 0) Heartbeat / Index
            current_idx = int(await self.nodes["PCBIndexCurrent"].read_value())
            current_idx += 1
            await self.nodes["PCBIndexCurrent"].write_value(ua.Variant(current_idx, ua.VariantType.UInt32))

            # Read target values
            t_rate = float(await self.nodes["TargetPlacementRateCPH"].read_value())
            t_ct = float(await self.nodes["TargetCycleTimeS"].read_value())
            t_ax = float(await self.nodes["TargetAccuracyXum"].read_value())
            t_ay = float(await self.nodes["TargetAccuracyYum"].read_value())

            # 1) PlacementRate
            a_rate = float(await self.nodes["ActualPlacementRateCPH"].read_value())
            a_rate += 0.05 * (t_rate - a_rate) + random.uniform(-0.2, 0.2)
            await self.nodes["ActualPlacementRateCPH"].write_value(ua.Variant(a_rate, ua.VariantType.Double))
            self.model.actual_placement_rate_cph = a_rate

            # 2) CycleTime
            ct = float(await self.nodes["ActualCycleTimeS"].read_value())
            ct += 0.15 * (t_ct - ct) + random.uniform(-0.003, 0.003)
            ct = max(0.1, ct)
            await self.nodes["ActualCycleTimeS"].write_value(ua.Variant(ct, ua.VariantType.Double))

            # 3) VisionPassRate: stabil ≥ 99.5
            v = float(await self.nodes["VisionPassRatePct"].read_value())
            v = max(99.5, min(100.0, v + random.uniform(-0.02, 0.02)))
            await self.nodes["VisionPassRatePct"].write_value(ua.Variant(v, ua.VariantType.Double))

            # 4) Vacuum: weit unter Schwelle halten
            vac = float(await self.nodes["VacuumPressureKPa"].read_value())
            vac = min(vac + random.uniform(-0.2, 0.2), -65.0)
            await self.nodes["VacuumPressureKPa"].write_value(ua.Variant(vac, ua.VariantType.Double))

            # 5) Kopfpositionen kleine Jitter
            for key, step in [("HeadPosXmm", 0.1), ("HeadPosYmm", 0.08)]:
                pos = float(await self.nodes[key].read_value())
                pos = pos + random.uniform(-step, step)
                await self.nodes[key].write_value(ua.Variant(pos, ua.VariantType.Double))

            # 6) Feeder usage (Real consumption)
            use = random.choice([None, 1, 2, 3, 4, None])
            if use:
                feeder_key = f"Feeder{use:02d}Count"
                cnt = int(await self.nodes[feeder_key].read_value())
                # Decrease count (simulate picking) - NEVER auto-refill
                if cnt > 0:
                    new_cnt = max(0, cnt - random.randint(1, 5))
                    await self.nodes[feeder_key].write_value(ua.Variant(new_cnt, ua.VariantType.UInt32))
            
            # Stateful Feeder Low Level Check (independent of consumption)
            for i in range(1, 5):
                check_key = f"Feeder{i:02d}Count"
                val = int(await self.nodes[check_key].read_value())
                if val < 200:
                    if not self._feeder_low_state[i]:
                        alarms: List[str] = (await self.alarm_list_node.read_value()) or []
                        self._push_alarm(alarms, f"Info: Feeder {i:02d} Low Level ({val}) - Please Refill!", critical=False)
                        alarms = alarms[-20:]
                        await self.alarm_list_node.write_value(ua.Variant(alarms, ua.VariantType.String))
                        self._feeder_low_state[i] = True
                else:
                    if self._feeder_low_state[i]:
                        # Reset state if refilled (>= 200)
                        self._feeder_low_state[i] = False


            # 7) Calculate Order Progress based on Counts
            if random.random() < 0.5: # 50% Chance pro Tick (Schneller fuer User)
                current_completed = int(await self.nodes["PCBsCompletedGood"].read_value())
                total_order = int(await self.nodes["TotalPCBsOrder"].read_value())
                
                current_completed += 1
                await self.nodes["PCBsCompletedGood"].write_value(ua.Variant(current_completed, ua.VariantType.UInt32))
                
                # Update Progress
                new_prog = min(100.0, (current_completed / total_order) * 100.0)
                await self.nodes["ProductionOrderProgressPct"].write_value(ua.Variant(new_prog, ua.VariantType.Double))
                
                # Check for Order Completion
                if current_completed >= total_order:
                     # NEW ORDER LOGIC
                     import uuid
                     new_suffix = uuid.uuid4().hex[:4].upper()
                     new_order_id = f"PO-2024-ECU-{new_suffix}"
                     new_total = random.randint(1000, 9000)
                     
                     await self.nodes["ProductionOrder"].write_value(ua.Variant(new_order_id, ua.VariantType.String))
                     await self.nodes["TotalPCBsOrder"].write_value(ua.Variant(new_total, ua.VariantType.UInt32))
                     await self.nodes["PCBsCompletedGood"].write_value(ua.Variant(0, ua.VariantType.UInt32))
                     await self.nodes["ProductionOrderProgressPct"].write_value(ua.Variant(0.0, ua.VariantType.Double))
                     
                     # Log event
                     alarms: List[str] = (await self.alarm_list_node.read_value()) or []
                     self._push_alarm(alarms, f"Order finished. Started new order {new_order_id}")
                     alarms = alarms[-20:]
                     await self.alarm_list_node.write_value(ua.Variant(alarms, ua.VariantType.String))

            # 8) Accuracy jitter um Ziel
            ax = float(await self.nodes["ActualAccuracyXum"].read_value())
            ay = float(await self.nodes["ActualAccuracyYum"].read_value())
            ax += 0.2 * (t_ax - ax) + random.uniform(-0.05, 0.05)
            ay += 0.2 * (t_ay - ay) + random.uniform(-0.05, 0.05)
            await self.nodes["ActualAccuracyXum"].write_value(ua.Variant(ax, ua.VariantType.Double))
            await self.nodes["ActualAccuracyYum"].write_value(ua.Variant(ay, ua.VariantType.Double))

        # Alarme nach PDF
        alarms: List[str] = (await self.alarm_list_node.read_value()) or []
        await self._check_dev("PlacementRate", "TargetPlacementRateCPH", "ActualPlacementRateCPH", alarms)
        await self._check_dev("CycleTime", "TargetCycleTimeS", "ActualCycleTimeS", alarms)
        await self._check_dev("HeadAccel", "TargetHeadAccelG", "ActualHeadAccelG", alarms)

        # Spezialalarme
        if abs(await self.nodes["ActualAccuracyXum"].read_value()) > 25.0 or abs(await self.nodes["ActualAccuracyYum"].read_value()) > 25.0:
            self._push_alarm(alarms, "Placement accuracy exceeded ±25 μm")
        if float(await self.nodes["VisionPassRatePct"].read_value()) < 99.0:
            self._push_alarm(alarms, "Vision system pass rate below 99%")
        if float(await self.nodes["VacuumPressureKPa"].read_value()) > -60.0:
            self._push_alarm(alarms, "Vacuum pressure insufficient for reliable pickup")
        
        # Generic Feeder Empty Check (Stateful)
        for i in range(1, 5):
            if int(await self.nodes[f"Feeder{i:02d}Count"].read_value()) <= 0:
                 if not self._feeder_empty_state[i]:
                     self._push_alarm(alarms, f"Feeder {i:02d} empty")
                     self._feeder_empty_state[i] = True
            else:
                 self._feeder_empty_state[i] = False         

        # Process Pending Alarms (One per cycle for sequential logs)
        if self._pending_alarms:
             msg, crit = self._pending_alarms.pop(0)
             await self.alarm_list_node.write_value(ua.Variant(msg, ua.VariantType.String))
             
             if crit:
                 self._last_push = True
                 await self.current_error_node.write_value(ua.Variant(msg, ua.VariantType.String))

        # Status-Handling (Trigger Transition)
        if self._last_push:
            await self.status_node.write_value(ua.Variant("Error", ua.VariantType.String))
            self.model.status = "Error"
        
        # Auto-Recovery Logic:
        # When machine is in Error state AND all feeders have been refilled (count > 0),
        # the machine automatically resumes Running without manual intervention.
        current_status = await self.status_node.read_value()
        if current_status == "Error" and not self._last_push:
            # Check all feeders explicitly (await doesn't work in generator expressions)
            all_feeders_ok = True
            for i in range(1, 5):
                feeder_val = int(await self.nodes[f"Feeder{i:02d}Count"].read_value())
                if feeder_val <= 0:
                    all_feeders_ok = False
                    break
            
            no_pending_critical = not any(crit for _, crit in self._pending_alarms)
            
            if all_feeders_ok and no_pending_critical:
                # Auto-resume
                await self.status_node.write_value(ua.Variant("Running", ua.VariantType.String))
                self.model.status = "Running"
                await self.current_error_node.write_value(ua.Variant("", ua.VariantType.String))
                self._pending_alarms.clear()
        
        # Reset Trigger
        self._last_push = False

    def _push_alarm(self, alarms: List[str], text: str, critical: bool = True):
        # Queue for sequential processing in _cycle
        self._pending_alarms.append((text, critical))

    @uamethod
    async def simulate_error(self, parent):
        import random
        errors = [
            "Emergency Stop Button Pressed",
            "Feeder Jammed",
            "Nozzle Clogged",
            "Vision Camera Failure",
            "Safety Door Open"
        ]
        msg = f"Random Fault: {random.choice(errors)}"
        
        # Queue alarm for next cycle (prevents overwrite race condition)
        self._pending_alarms.append((f"Error: {msg}", True))
        
        # Set Error Status immediately
        await self.status_node.write_value(ua.Variant("Error", ua.VariantType.String))
        self.model.status = "Error"

    async def _check_dev(self, name: str, target_key: str, actual_key: str, alarms: List[str]):
        tnode = self.nodes.get(target_key)
        anode = self.nodes.get(actual_key)
        if not tnode or not anode:
            return
        t = float(await tnode.read_value())
        a = float(await anode.read_value())
        alarm, text, _ = self.model._dev.record(name, t, a)
        if alarm:
            self._push_alarm(alarms, text)


async def main():
    logging.basicConfig(level=logging.INFO)
    pnp = PickAndPlaceServer()
    await pnp.init()
    # Logge Port
    logging.info(f"OPC UA Server '{APP_NAME}' listening on {ENDPOINT}")
    try:
        await pnp.run()
    except Exception as e:
        logging.error(f"Uncaught exception in server main loop: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
