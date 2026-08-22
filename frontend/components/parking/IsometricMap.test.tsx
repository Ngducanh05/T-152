import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { canonicalMap } from "@/test/fixtures";
import type { MapNode } from "@/lib/types";
import { IsometricMap } from "./IsometricMap";

afterEach(cleanup);

describe("IsometricMap", () => {
  it("render ra data-testid='isometric-map', đúng 40 .iso-bay, có .iso-slab-top và aria-label chứa 'Phối cảnh Tầng 1'", () => {
    const f1Nodes = canonicalMap.nodes.filter((n) => n.floor_id === "F1");
    const f1Slots = canonicalMap.slots.filter((s) => s.floor_id === "F1");

    const { container } = render(
      <IsometricMap
        floorId="F1"
        nodes={f1Nodes}
        edges={canonicalMap.edges}
        slots={f1Slots}
      />,
    );

    const mapSvg = screen.getByTestId("isometric-map");
    expect(mapSvg).toBeDefined();
    expect(mapSvg.getAttribute("aria-label")).toContain("Phối cảnh Tầng 1");

    const bays = container.querySelectorAll(".iso-bay");
    expect(bays).toHaveLength(40);

    const slabTop = container.querySelector(".iso-slab-top");
    expect(slabTop).toBeDefined();
    expect(slabTop).not.toBeNull();
  });

  it("F2 không có nhãn LỐI VÀO và LỐI RA", () => {
    const f2Nodes: MapNode[] = [
      { id: "F2-RAMP", floor_id: "F2", type: "RAMP", x: 85, y: 75 },
      { id: "F2-ELEVATOR", floor_id: "F2", type: "ELEVATOR", x: 50, y: 92 },
    ];
    render(
      <IsometricMap
        floorId="F2"
        nodes={f2Nodes}
        edges={[]}
        slots={[]}
      />,
    );

    expect(screen.queryByText("LỐI VÀO")).toBeNull();
    expect(screen.queryByText("LỐI RA")).toBeNull();
  });

  // AC-21, AC-24
  it("AC-21, AC-24: Ở chế độ iso có đúng 40 nút ô đỗ với aria-label đầy đủ", () => {
    const f1Nodes = canonicalMap.nodes.filter((n) => n.floor_id === "F1");
    const f1Slots = canonicalMap.slots.filter((s) => s.floor_id === "F1");

    render(
      <IsometricMap
        floorId="F1"
        nodes={f1Nodes}
        edges={canonicalMap.edges}
        slots={f1Slots}
      />,
    );

    const slotButtons = screen.getAllByRole("button", { name: /Ô đỗ/ });
    expect(slotButtons).toHaveLength(40);

    const slotA01 = screen.getByRole("button", { name: /Ô đỗ F1-A01, Khu A/ });
    expect(slotA01).toBeDefined();
    expect(slotA01).toHaveClass("map-slot--iso");
  });

  // AC-22
  it("AC-22: Ở chế độ iso bấm 1 ô gọi onSelectSlot với đúng slotId", () => {
    const f1Nodes = canonicalMap.nodes.filter((n) => n.floor_id === "F1");
    const f1Slots = canonicalMap.slots.filter((s) => s.floor_id === "F1");
    const onSelectSlot = vi.fn();

    render(
      <IsometricMap
        floorId="F1"
        nodes={f1Nodes}
        edges={canonicalMap.edges}
        slots={f1Slots}
        onSelectSlot={onSelectSlot}
      />,
    );

    const slotA02 = screen.getByRole("button", { name: /Ô đỗ F1-A02, Khu A/ });
    fireEvent.click(slotA02);
    expect(onSelectSlot).toHaveBeenCalledWith("F1-A02");
  });

  // AC-23
  it("AC-23: Ở chế độ iso ô có báo cáo mở gọi onOpenReportedSlot, không gọi onSelectSlot", () => {
    const f1Nodes = canonicalMap.nodes.filter((n) => n.floor_id === "F1");
    const f1Slots = canonicalMap.slots.filter((s) => s.floor_id === "F1");
    const onSelectSlot = vi.fn();
    const onOpenReportedSlot = vi.fn();

    render(
      <IsometricMap
        floorId="F1"
        nodes={f1Nodes}
        edges={canonicalMap.edges}
        slots={f1Slots}
        openReportCountBySlot={{ "F1-A01": 2 }}
        onSelectSlot={onSelectSlot}
        onOpenReportedSlot={onOpenReportedSlot}
      />,
    );

    const reportedSlot = screen.getByRole("button", { name: /Ô đỗ F1-A01, Khu A/ });
    fireEvent.click(reportedSlot);
    expect(onOpenReportedSlot).toHaveBeenCalledWith("F1-A01");
    expect(onSelectSlot).not.toHaveBeenCalled();
  });

  it("bỏ qua slot thiếu MapNode, không render nút ở toạ độ giả (0,0)", () => {
    const f1Slots = canonicalMap.slots.filter((s) => s.floor_id === "F1");
    const partialNodes = canonicalMap.nodes.filter(
      (n) => n.floor_id === "F1" && (n.type !== "SLOT" || n.id.startsWith("F1-A")),
    );

    render(
      <IsometricMap
        floorId="F1"
        nodes={partialNodes}
        edges={[]}
        slots={f1Slots}
      />,
    );

    const slotButtons = screen.getAllByRole("button", { name: /Ô đỗ/ });
    expect(slotButtons).toHaveLength(10);
  });

  it("toàn bộ 40 ô đỗ có toạ độ tâm phân biệt và có thể nhận focus", () => {
    const f1Nodes = canonicalMap.nodes.filter((n) => n.floor_id === "F1");
    const f1Slots = canonicalMap.slots.filter((s) => s.floor_id === "F1");

    const { container } = render(
      <IsometricMap
        floorId="F1"
        nodes={f1Nodes}
        edges={canonicalMap.edges}
        slots={f1Slots}
      />,
    );

    const wrappers = container.querySelectorAll(".map-slot-wrapper--iso");
    expect(wrappers).toHaveLength(40);
    const positions = new Set<string>();

    for (const wrap of wrappers) {
      const htmlWrap = wrap as HTMLElement;
      const left = htmlWrap.style.left;
      const top = htmlWrap.style.top;
      const key = `${left},${top}`;
      expect(positions.has(key)).toBe(false);
      positions.add(key);

      const btn = wrap.querySelector("button");
      expect(btn).not.toBeNull();
      btn!.focus();
      expect(document.activeElement).toBe(btn);
    }

    expect(positions.size).toBe(40);
  });

  it("focus ô A01 trước, sau đó click ô liền kề A02 vẫn gọi onSelectSlot('F1-A02')", () => {
    const f1Nodes = canonicalMap.nodes.filter((n) => n.floor_id === "F1");
    const f1Slots = canonicalMap.slots.filter((s) => s.floor_id === "F1");
    const onSelectSlot = vi.fn();

    render(
      <IsometricMap
        floorId="F1"
        nodes={f1Nodes}
        edges={canonicalMap.edges}
        slots={f1Slots}
        onSelectSlot={onSelectSlot}
      />,
    );

    const slotA01 = screen.getByRole("button", { name: /Ô đỗ F1-A01, Khu A/ });
    const slotA02 = screen.getByRole("button", { name: /Ô đỗ F1-A02, Khu A/ });

    // Focus ô A01
    slotA01.focus();
    expect(document.activeElement).toBe(slotA01);

    // Click ô A02 kế bên
    fireEvent.click(slotA02);
    expect(onSelectSlot).toHaveBeenCalledWith("F1-A02");
  });

  it("hiển thị badge và report warning trong wrapper không bị clip", () => {
    const f1Nodes = canonicalMap.nodes.filter((n) => n.floor_id === "F1");
    const f1Slots = canonicalMap.slots.filter((s) => s.floor_id === "F1");

    const { container } = render(
      <IsometricMap
        floorId="F1"
        nodes={f1Nodes}
        edges={canonicalMap.edges}
        slots={f1Slots}
        recommendedSlotIds={["F1-A01"]}
        activeReservationSlotId="F1-A02"
        parkedVehicleSlotId="F1-A03"
        openReportCountBySlot={{ "F1-A04": 3 }}
      />,
    );

    const badgesLayer = container.querySelectorAll(".map-slot-badges--iso");
    expect(badgesLayer.length).toBeGreaterThan(0);

    expect(screen.getByText("Đề xuất")).toBeDefined();
    expect(screen.getByText("Đã giữ")).toBeDefined();
    expect(screen.getByText("Xe của bạn")).toBeDefined();
    expect(screen.getByText("3")).toBeDefined();
  });
});
