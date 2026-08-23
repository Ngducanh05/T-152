import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  MapEdge,
  MapNode,
  ParkingMap as ParkingMapData,
  ParkingSlot,
} from "@/lib/types";
import { getDisplayPoint } from "@/lib/map-geometry";
import { canonicalMap, parkingStatus } from "@/test/fixtures";

import { ParkingMap } from "./ParkingMap";

afterEach(cleanup);

function fixture() {
  const map: ParkingMapData = canonicalMap;
  return { map, slots: map.slots, status: parkingStatus };
}

describe("ParkingMap", () => {
  it("renders all 40 canonical slots including zone D and structured highlights", () => {
    const { map, slots, status } = fixture();

    const { container } = render(
      <ParkingMap
        map={map}
        slots={slots}
        status={status}
        recommendedSlotIds={["F1-D01"]}
        selectedSlotId="F1-A02"
        activeReservationSlotId="F1-A01"
        parkedVehicleSlotId="F1-B01"
        currentLocationNodeId="F1-CP1"
      />,
    );

    expect(screen.getAllByRole("button", { name: /Ô đỗ/ })).toHaveLength(40);
    expect(screen.getByRole("button", { name: /F1-D10, Khu D/ })).toBeDefined();
    expect(screen.getByRole("button", { name: /F1-A01.*Đã giữ.*Chỗ đã giữ/ }).getAttribute("data-status")).toBe("RESERVED");
    expect(screen.getByRole("button", { name: /F1-D01.*Có sạc điện.*Được đề xuất/ })).toBeDefined();
    expect(screen.queryByTestId("current-location")).toBeNull();
    expect(container.querySelector('[data-node-id="F1-CP1"]')).toBeNull();
    expect(getDisplayPoint({ id: "F1-ELEVATOR", floor_id: "F1", type: "ELEVATOR", x: 50, y: 92 })).toEqual([50, 96]);
    expect(container.querySelector(".elevator-road")?.getAttribute("d")).toBe("M 50 50 L 50 90");
  });

  it("lays slots out as usable bays and routes along orthogonal driving lanes", () => {
    const { map, slots, status } = fixture();

    render(
      <ParkingMap
        map={map}
        slots={slots}
        status={status}
        route={{
          path: ["F1-ENTRANCE", "F1-CP1", "F1-D-W", "F1-D01"],
          distance_m: 76,
          polyline: [[0, 50], [15, 50], [58, 70], [58, 74]],
        }}
      />,
    );

    const slot = screen.getByRole("button", { name: /F1-D01, Khu D/ });
    expect(slot.getAttribute("data-x")).toBe("55");
    expect(slot.getAttribute("data-y")).toBe("61");
    expect(screen.getByTestId("route-polyline").getAttribute("points")).toBe(
      "0,50 15,50 50,50 55,50 55,61",
    );
  });

  it("keeps the slot status styling while adding an accessible OPEN report warning", () => {
    const { map, slots, status } = fixture();
    const onOpenReportedSlot = vi.fn();
    const onSelectSlot = vi.fn();
    render(
      <ParkingMap
        map={map}
        slots={slots}
        status={status}
        openReportCountBySlot={{ "F1-A01": 2 }}
        onOpenReportedSlot={onOpenReportedSlot}
        onSelectSlot={onSelectSlot}
      />,
    );

    const warnedSlot = screen.getByRole("button", {
      name: /F1-A01.*Đã giữ.*2 báo cáo đang mở/,
    });
    expect(warnedSlot).toHaveClass("status-reserved", "has-open-reports");
    expect(warnedSlot.querySelector(".map-slot-report-warning")).toHaveTextContent("2");
    fireEvent.click(warnedSlot);
    expect(onOpenReportedSlot).toHaveBeenCalledWith("F1-A01");
    expect(onSelectSlot).toHaveBeenCalledWith("F1-A01");

    const normalSlot = screen.getByRole("button", { name: /F1-A02, Khu A/ });
    expect(normalSlot).toHaveClass("status-available");
    expect(normalSlot).not.toHaveClass("has-open-reports");
    fireEvent.click(normalSlot);
    expect(onSelectSlot).toHaveBeenCalledWith("F1-A02");
  });

  it("reconstructs all F2/F3 bays from the canonical F1 geometry in both map modes", () => {
    const { map, slots, status } = fixture();
    const cloneSlots = (floorId: "F2" | "F3"): ParkingSlot[] =>
      slots.map((slot) => ({
        ...slot,
        id: slot.id.replace("F1-", `${floorId}-`),
        floor_id: floorId,
        node_id: slot.node_id.replace("F1-", `${floorId}-`),
      }));

    render(
      <ParkingMap
        map={map}
        slots={[...slots, ...cloneSlots("F2"), ...cloneSlots("F3")]}
        status={status}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Tầng 2:/ }));
    expect(screen.getAllByRole("button", { name: /Ô đỗ F2-/ })).toHaveLength(40);

    fireEvent.click(screen.getByRole("button", { name: "Phối cảnh hầm" }));
    expect(screen.getAllByRole("button", { name: /Ô đỗ F2-/ })).toHaveLength(40);

    fireEvent.click(screen.getByRole("button", { name: /Tầng 3:/ }));
    expect(screen.getAllByRole("button", { name: /Ô đỗ F3-/ })).toHaveLength(40);
    expect(screen.getByTestId("isometric-map").getAttribute("aria-label")).toContain("Tầng 3");
  });

  it("shows complete Vietnamese gate and inter-floor labels without duplicates", () => {
    const { map, slots, status } = fixture();
    const facilityNodes: MapNode[] = [
      { id: "F1-EXIT", floor_id: "F1", type: "EXIT", x: 100, y: 50 },
      { id: "F1-RAMP", floor_id: "F1", type: "RAMP", x: 85, y: 75 },
      { id: "F1-ELEVATOR", floor_id: "F1", type: "ELEVATOR", x: 50, y: 92 },
      { id: "F2-RAMP", floor_id: "F2", type: "RAMP", x: 85, y: 75 },
      { id: "F3-RAMP", floor_id: "F3", type: "RAMP", x: 85, y: 75 },
    ];

    const { container } = render(
      <ParkingMap
        map={{ ...map, nodes: [...map.nodes, ...facilityNodes] }}
        slots={slots}
        status={status}
      />,
    );

    expect(screen.getByText("LỐI VÀO").getAttribute("x")).toBe("4.5");
    expect(screen.getByText("LỐI RA").getAttribute("x")).toBe("95.5");
    expect(screen.queryByText("ENTRANCE")).toBeNull();
    expect(screen.queryByText("EXIT")).toBeNull();
    expect(screen.queryByText("RAMP")).toBeNull();
    expect(screen.queryByText("ELEVATOR")).toBeNull();
    expect(container.querySelectorAll(".map-ramp-indicator text")).toHaveLength(1);
    expect(container.querySelector(".map-ramp-indicator text")).toHaveTextContent("Xuống F2");
    expect(container.querySelectorAll(".map-elevator-indicator text")).toHaveLength(1);
    expect(container.querySelector(".map-elevator-indicator text")).toHaveTextContent("THANG MÁY");

    fireEvent.click(screen.getByRole("button", { name: /Tầng 2:/ }));
    expect(screen.getByText("↑ Lên F1")).toBeDefined();
    expect(screen.getByText("↓ Xuống F3")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: /Tầng 3:/ }));
    expect(screen.getByText("↑ Lên F2")).toBeDefined();
  });

  it("AC-19: Render ParkingMap không truyền defaultViewMode mặc định là 2D phẳng", () => {
    const { map, slots, status } = fixture();
    render(<ParkingMap map={map} slots={slots} status={status} />);

    expect(screen.getByTestId("parking-map")).toBeDefined();
    expect(screen.queryByTestId("isometric-map")).toBeNull();
  });

  it("AC-20: Bấm nút Phối cảnh hầm chuyển sang chế độ isometric", () => {
    const { map, slots, status } = fixture();
    render(<ParkingMap map={map} slots={slots} status={status} />);

    const isoToggle = screen.getByRole("button", { name: "Phối cảnh hầm" });
    fireEvent.click(isoToggle);

    expect(screen.getByTestId("isometric-map")).toBeDefined();
    expect(screen.queryByTestId("parking-map")).toBeNull();
  });

  it("only renders vehicle artwork in the isometric view", () => {
    const { map, slots, status } = fixture();
    const { container } = render(
      <ParkingMap map={map} slots={slots} status={status} />,
    );

    expect(container.querySelector(".map-slot-car")).toBeNull();
    expect(container.querySelector(".iso-car")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Phối cảnh hầm" }));
    expect(container.querySelectorAll(".iso-car").length).toBeGreaterThan(0);
  });

  it("AC-25: Bấm Sơ đồ phẳng để quay lại chế độ 2D", () => {
    const { map, slots, status } = fixture();
    render(
      <ParkingMap
        map={map}
        slots={slots}
        status={status}
        defaultViewMode="iso"
      />,
    );

    expect(screen.getByTestId("isometric-map")).toBeDefined();

    const flatToggle = screen.getByRole("button", { name: "Sơ đồ phẳng" });
    fireEvent.click(flatToggle);

    expect(screen.getByTestId("parking-map")).toBeDefined();
    expect(screen.queryByTestId("isometric-map")).toBeNull();
  });

  it("AC-26: Đổi tầng khi đang ở chế độ iso vẫn giữ chế độ iso và đổi nội dung sang tầng mới (không render route cũ)", () => {
    const { map, slots, status } = fixture();
    const facilityNodes: MapNode[] = [
      { id: "F2-RAMP", floor_id: "F2", type: "RAMP", x: 85, y: 75 },
      { id: "F2-ELEVATOR", floor_id: "F2", type: "ELEVATOR", x: 50, y: 92 },
      { id: "F2-A-W", floor_id: "F2", type: "AISLE", x: 25, y: 30 },
      { id: "F2-A01", floor_id: "F2", type: "SLOT", x: 25, y: 22 },
    ];
    const f2Slots: ParkingSlot[] = [
      {
        id: "F2-A01",
        floor_id: "F2",
        zone_id: "A",
        node_id: "F2-A-W",
        status: "AVAILABLE",
        has_charger: false,
        is_accessible: false,
        version: 1,
        occupied_by_vehicle_id: null,
      },
    ];
    render(
      <ParkingMap
        map={{ ...map, nodes: [...map.nodes, ...facilityNodes] }}
        slots={[...slots, ...f2Slots]}
        status={status}
        defaultViewMode="iso"
        route={{
          path: ["F1-ENTRANCE", "F1-CP1", "F1-D-W", "F1-D01"],
          distance_m: 76,
          polyline: [
            [0, 50],
            [15, 50],
            [58, 70],
            [58, 74],
          ],
        }}
      />,
    );

    expect(screen.getByTestId("isometric-map")).toBeDefined();
    expect(screen.getByTestId("isometric-map").getAttribute("aria-label")).toContain("Phối cảnh Tầng 1");
    expect(screen.getByTestId("route-polyline")).toBeDefined();

    // Chuyển sang Tầng 2
    fireEvent.click(screen.getByRole("button", { name: /Tầng 2:/ }));
    expect(screen.getByTestId("isometric-map")).toBeDefined();
    expect(screen.getByTestId("isometric-map").getAttribute("aria-label")).toContain("Phối cảnh Tầng 2");
    // Route thuộc F1 không được vẽ trên F2
    expect(screen.queryByTestId("route-polyline")).toBeNull();
  });

  it("chế độ 2D phẳng cũng không render route của tầng khác khi đổi sang F2", () => {
    const { map, slots, status } = fixture();
    const facilityNodes: MapNode[] = [
      { id: "F2-RAMP", floor_id: "F2", type: "RAMP", x: 85, y: 75 },
      { id: "F2-ELEVATOR", floor_id: "F2", type: "ELEVATOR", x: 50, y: 92 },
      { id: "F2-A-W", floor_id: "F2", type: "AISLE", x: 25, y: 30 },
      { id: "F2-A01", floor_id: "F2", type: "SLOT", x: 25, y: 22 },
    ];
    const f2Slots: ParkingSlot[] = [
      {
        id: "F2-A01",
        floor_id: "F2",
        zone_id: "A",
        node_id: "F2-A-W",
        status: "AVAILABLE",
        has_charger: false,
        is_accessible: false,
        version: 1,
        occupied_by_vehicle_id: null,
      },
    ];
    render(
      <ParkingMap
        map={{ ...map, nodes: [...map.nodes, ...facilityNodes] }}
        slots={[...slots, ...f2Slots]}
        status={status}
        defaultViewMode="flat"
        route={{
          path: ["F1-ENTRANCE", "F1-CP1", "F1-D-W", "F1-D01"],
          distance_m: 76,
          polyline: [
            [0, 50],
            [15, 50],
            [58, 70],
            [58, 74],
          ],
        }}
      />,
    );

    expect(screen.getByTestId("parking-map")).toBeDefined();
    expect(screen.getByTestId("route-polyline")).toBeDefined();

    // Chuyển sang Tầng 2 ở chế độ 2D
    fireEvent.click(screen.getByRole("button", { name: /Tầng 2:/ }));
    expect(screen.getByTestId("parking-map")).toBeDefined();
    expect(screen.queryByTestId("route-polyline")).toBeNull();
  });

  it("AC-31: Cắt chính xác đoạn F2 của route xuyên tầng ở cả chế độ phẳng và isometric", () => {
    const { map, slots, status } = fixture();
    const facilityNodes: MapNode[] = [
      { id: "F2-RAMP", floor_id: "F2", type: "RAMP", x: 85, y: 75 },
      { id: "F2-CP3", floor_id: "F2", type: "CHECKPOINT", x: 85, y: 50 },
      { id: "F2-D-W", floor_id: "F2", type: "AISLE", x: 58, y: 70 },
      { id: "F2-D01", floor_id: "F2", type: "SLOT", x: 58, y: 74 },
    ];
    const facilityEdges: MapEdge[] = [
      { from_node: "F2-RAMP", to_node: "F2-CP3", distance_m: 25, bidirectional: true, enabled: true, allowed_mode: null },
      { from_node: "F2-CP3", to_node: "F2-D-W", distance_m: 22, bidirectional: true, enabled: true, allowed_mode: null },
      { from_node: "F2-D-W", to_node: "F2-D01", distance_m: 4, bidirectional: true, enabled: true, allowed_mode: null },
    ];
    const f2Slots: ParkingSlot[] = [
      {
        id: "F2-D01",
        floor_id: "F2",
        zone_id: "D",
        node_id: "F2-D-W",
        status: "AVAILABLE",
        has_charger: false,
        is_accessible: false,
        version: 1,
        occupied_by_vehicle_id: null,
      },
    ];

    const multiFloorRoute = {
      path: [
        "F1-ENTRANCE",
        "F1-CP1",
        "F1-D-W",
        "F1-D01",
        "F2-RAMP",
        "F2-CP3",
        "F2-D-W",
        "F2-D01",
      ],
      distance_m: 150,
      polyline: [
        [0, 50],
        [15, 50],
        [58, 70],
        [58, 74],
        [85, 75],
        [85, 50],
        [58, 70],
        [58, 74],
      ] as [number, number][],
    };

    render(
      <ParkingMap
        map={{
          ...map,
          nodes: [...map.nodes, ...facilityNodes],
          edges: [...map.edges, ...facilityEdges],
        }}
        slots={[...slots, ...f2Slots]}
        status={status}
        defaultViewMode="flat"
        route={multiFloorRoute}
      />,
    );

    // 1. Ở F1 phẳng: route vẽ đúng đoạn F1
    expect(screen.getByTestId("route-polyline").getAttribute("points")).toBe(
      "0,50 15,50 50,50 55,50 55,61",
    );

    // 2. Chuyển sang F2 phẳng: route cắt đúng đoạn F2 (85,75 -> 85,50 -> 50,50 -> 55,50 -> 55,61)
    fireEvent.click(screen.getByRole("button", { name: /Tầng 2:/ }));
    const flatF2Points = screen.getByTestId("route-polyline").getAttribute("points");
    expect(flatF2Points).toBe("85,75 85,50 50,50 55,50 55,61");
    expect(flatF2Points?.startsWith("0,50")).toBe(false);

    // 3. Chuyển sang Phối cảnh hầm ở F2: route iso F2 có points khớp chính xác projected iso
    fireEvent.click(screen.getByRole("button", { name: "Phối cảnh hầm" }));
    const isoF2Polyline = screen.getByTestId("route-polyline");
    expect(isoF2Polyline).toBeDefined();
    const isoF2Points = isoF2Polyline.getAttribute("points");
    expect(isoF2Points).not.toBeNull();
    expect(isoF2Points?.startsWith("0,50")).toBe(false);
  });
});


