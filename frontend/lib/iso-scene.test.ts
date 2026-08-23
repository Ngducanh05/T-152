import { describe, expect, it } from "vitest";

import { canonicalMap } from "@/test/fixtures";
import { buildIsoRamp } from "@/lib/iso-geometry";
import type { MapNode } from "@/lib/types";
import {
  RAMP_EAST_CENTER,
  RAMP_WEST_CENTER,
  ROAD_W_RING,
  buildIsoScene,
} from "./iso-scene";

describe("iso-scene", () => {
  it("AC-13: buildIsoScene với fixture 1 tầng trả về đúng 40 bays", () => {
    const scene = buildIsoScene({
      floorId: "F1",
      nodes: canonicalMap.nodes.filter((n) => n.floor_id === "F1"),
      edges: canonicalMap.edges,
      slots: canonicalMap.slots.filter((s) => s.floor_id === "F1"),
      route: null,
      currentLocationNodeId: null,
    });

    expect(scene.bays).toHaveLength(40);
  });

  it("AC-14: scene.bays được sắp xếp tăng dần theo depth (không giảm)", () => {
    const scene = buildIsoScene({
      floorId: "F1",
      nodes: canonicalMap.nodes.filter((n) => n.floor_id === "F1"),
      edges: canonicalMap.edges,
      slots: canonicalMap.slots.filter((s) => s.floor_id === "F1"),
      route: null,
      currentLocationNodeId: null,
    });

    for (let i = 0; i < scene.bays.length - 1; i += 1) {
      expect(scene.bays[i].depth).toBeLessThanOrEqual(scene.bays[i + 1].depth);
    }
  });

  it("AC-15: buildIsoScene cho F2 không có prop ENTRANCE và EXIT", () => {
    const f2Nodes: MapNode[] = [
      { id: "F2-RAMP", floor_id: "F2", type: "RAMP", x: 85, y: 75 },
      { id: "F2-ELEVATOR", floor_id: "F2", type: "ELEVATOR", x: 50, y: 92 },
    ];
    const scene = buildIsoScene({
      floorId: "F2",
      nodes: f2Nodes,
      edges: [],
      slots: [],
      route: null,
      currentLocationNodeId: null,
    });

    const entranceProp = scene.props.find((p) => p.kind === "ENTRANCE");
    const exitProp = scene.props.find((p) => p.kind === "EXIT");
    expect(entranceProp).toBeUndefined();
    expect(exitProp).toBeUndefined();
  });

  it("đặt hai dốc F2 bên ngoài mép đường và không che làn xe", () => {
    const scene = buildIsoScene({
      floorId: "F2",
      nodes: [
        { id: "F2-RAMP", floor_id: "F2", type: "RAMP", x: 85, y: 75 },
      ],
      edges: [],
      slots: [],
      route: null,
      currentLocationNodeId: null,
    });
    const rampUp = scene.props.find((prop) => prop.id === "F2-RAMP-up");
    const rampDown = scene.props.find((prop) => prop.id === "F2-RAMP-down");

    expect(rampUp?.ramp?.deck).toEqual(
      buildIsoRamp(RAMP_EAST_CENTER, 3.6, 4.5, 6).deck,
    );
    expect(rampDown?.ramp?.deck).toEqual(
      buildIsoRamp(RAMP_WEST_CENTER, 3.6, 4.5, -6).deck,
    );
    expect(RAMP_EAST_CENTER[0] - 3.6).toBeGreaterThan(80 + ROAD_W_RING / 2);
    expect(RAMP_WEST_CENTER[0] + 3.6).toBeLessThan(20 - ROAD_W_RING / 2);
  });

  it("AC-16: buildIsoScene cho F1 có đủ prop ENTRANCE, EXIT, ELEVATOR và 3 CHECKPOINT khi có nodes tương ứng", () => {
    const f1Nodes: MapNode[] = [
      { id: "F1-ENTRANCE", floor_id: "F1", type: "ENTRANCE", x: 0, y: 50 },
      { id: "F1-EXIT", floor_id: "F1", type: "EXIT", x: 100, y: 50 },
      { id: "F1-ELEVATOR", floor_id: "F1", type: "ELEVATOR", x: 50, y: 92 },
      { id: "F1-CP1", floor_id: "F1", type: "CHECKPOINT", x: 15, y: 50 },
      { id: "F1-CP2", floor_id: "F1", type: "CHECKPOINT", x: 50, y: 50 },
      { id: "F1-CP3", floor_id: "F1", type: "CHECKPOINT", x: 85, y: 50 },
    ];
    const scene = buildIsoScene({
      floorId: "F1",
      nodes: f1Nodes,
      edges: [],
      slots: [],
      route: null,
      currentLocationNodeId: null,
    });

    expect(scene.props.find((p) => p.kind === "ENTRANCE")).toBeDefined();
    expect(scene.props.find((p) => p.kind === "EXIT")).toBeDefined();
    expect(scene.props.find((p) => p.kind === "ELEVATOR")).toBeDefined();
    const checkpoints = scene.props.filter((p) => p.kind === "CHECKPOINT");
    expect(checkpoints).toHaveLength(3);
  });

  it("AC-17: Số ô OCCUPIED đúng bằng số bay có car !== null", () => {
    const slots = canonicalMap.slots.filter((s) => s.floor_id === "F1");
    const occupiedCount = slots.filter((s) => s.status === "OCCUPIED").length;

    const scene = buildIsoScene({
      floorId: "F1",
      nodes: canonicalMap.nodes.filter((n) => n.floor_id === "F1"),
      edges: canonicalMap.edges,
      slots,
      route: null,
      currentLocationNodeId: null,
    });

    const carBays = scene.bays.filter((b) => b.car !== null);
    expect(carBays).toHaveLength(occupiedCount);
  });

  it("dựng đầy đủ slab, zones, roads, labels và route nhưng ẩn vị trí checkpoint", () => {
    const scene = buildIsoScene({
      floorId: "F1",
      nodes: canonicalMap.nodes.filter((n) => n.floor_id === "F1"),
      edges: canonicalMap.edges,
      slots: canonicalMap.slots.filter((s) => s.floor_id === "F1"),
      route: {
        path: ["F1-ENTRANCE", "F1-CP1"],
        distance_m: 15,
        polyline: [
          [0, 50],
          [15, 50],
        ],
      },
      currentLocationNodeId: "F1-CP1",
    });

    expect(scene.slab.top).toHaveLength(4);
    expect(scene.zones).toHaveLength(4);
    expect(scene.roads).toHaveLength(5);
    expect(scene.labels.length).toBeGreaterThan(0);
    expect(scene.routePoints).toBeDefined();
    expect(scene.currentLocationAt).toBeNull();
  });

  it("bỏ qua slot không có MapNode trong danh sách nodes (không tạo dummy node)", () => {
    const f1Slots = canonicalMap.slots.filter((s) => s.floor_id === "F1");
    // Chỉ truyền node của 10 slot zone A
    const partialNodes = canonicalMap.nodes.filter(
      (n) => n.floor_id === "F1" && (n.type !== "SLOT" || n.id.startsWith("F1-A")),
    );

    const scene = buildIsoScene({
      floorId: "F1",
      nodes: partialNodes,
      edges: [],
      slots: f1Slots, // 40 slots
      route: null,
      currentLocationNodeId: null,
    });

    expect(scene.bays).toHaveLength(10);
    expect(scene.bays.every((b) => b.slotId.startsWith("F1-A"))).toBe(true);
  });

  it("không render route khi route thuộc tầng khác (dưới 2 node thuộc tầng hiện tại)", () => {
    const f2Nodes: MapNode[] = [
      { id: "F2-RAMP", floor_id: "F2", type: "RAMP", x: 85, y: 75 },
      { id: "F2-ELEVATOR", floor_id: "F2", type: "ELEVATOR", x: 50, y: 92 },
    ];

    const scene = buildIsoScene({
      floorId: "F2",
      nodes: f2Nodes,
      edges: [],
      slots: [],
      route: {
        path: ["F1-ENTRANCE", "F1-CP1", "F1-D-W", "F1-D01"],
        distance_m: 76,
        polyline: [[0, 50], [15, 50], [58, 70], [58, 74]],
      },
      currentLocationNodeId: null,
    });

    expect(scene.routePoints).toBeNull();
  });

  it("route có 3 ID nhưng thiếu ID ở giữa thì routePoints phải null (không nối tắt)", () => {
    const nodes: MapNode[] = [
      { id: "F1-ENTRANCE", floor_id: "F1", type: "ENTRANCE", x: 0, y: 50 },
      { id: "F1-CP2", floor_id: "F1", type: "CHECKPOINT", x: 50, y: 50 },
    ];

    const scene = buildIsoScene({
      floorId: "F1",
      nodes,
      edges: [],
      slots: [],
      route: {
        path: ["F1-ENTRANCE", "F1-CP1", "F1-CP2"], // F1-CP1 is missing in nodes
        distance_m: 50,
        polyline: [[0, 50], [15, 50], [50, 50]],
      },
      currentLocationNodeId: null,
    });

    expect(scene.routePoints).toBeNull();
  });
});
