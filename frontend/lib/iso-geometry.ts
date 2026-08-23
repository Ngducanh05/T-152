import type { MapPoint } from "@/lib/map-geometry";

/** Hằng số cos(30°) dùng cho phép chiếu isometric true 30°. */
export const ISO_COS = 0.8660254037844387;

/** Hằng số sin(30°) dùng cho phép chiếu isometric true 30°. */
export const ISO_SIN = 0.5;

/** Toạ độ gốc X trong hệ viewBox isometric (200x140). */
export const ISO_ORIGIN_X = 100;

/** Toạ độ gốc Y trong hệ viewBox isometric (200x140). */
export const ISO_ORIGIN_Y = 62;

/** Chiều rộng viewBox isometric. */
export const ISO_VIEW_W = 200;

/** Chiều cao viewBox isometric. */
export const ISO_VIEW_H = 140;

/** Ba mặt nhìn thấy được của khối hộp isometric. */
export interface IsoBoxFaces {
  top: MapPoint[];
  left: MapPoint[];
  right: MapPoint[];
}

/** Các mặt nhìn thấy được của mặt phẳng nghiêng (ramp). */
export interface IsoRampFaces {
  deck: MapPoint[];
  left: MapPoint[];
  right: MapPoint[];
  opening: MapPoint[] | null;
  centerLine: MapPoint[];
  sideLines: [MapPoint[], MapPoint[]];
  direction: "UP" | "DOWN";
}

/**
 * Nâng toạ độ màn hình lên theo trục thẳng đứng (giảm screenY).
 */
function lift(point: MapPoint, height: number): MapPoint {
  return [point[0], point[1] - height];
}

/**
 * Chiếu 1 điểm không gian nguồn (0-100) sang toạ độ viewBox isometric.
 */
export function projectIso(point: MapPoint): MapPoint {
  const [u, v] = point;
  const cu = u - 50;
  const cv = v - 50;
  const sx = (cu - cv) * ISO_COS;
  const sy = (cu + cv) * ISO_SIN;
  return [ISO_ORIGIN_X + sx, ISO_ORIGIN_Y + sy];
}

/**
 * Chiếu cả một chuỗi điểm. Dùng cho route và vạch kẻ đường.
 */
export function projectIsoPath(points: MapPoint[]): MapPoint[] {
  return points.map(projectIso);
}

/**
 * Khoá độ sâu để sắp xếp painter algorithm. Càng lớn nghĩa là càng gần người xem.
 */
export function isoDepth(point: MapPoint): number {
  return point[0] + point[1];
}

/**
 * 4 đỉnh đã chiếu của một hình chữ nhật nguồn. Thứ tự: sau, phải, trước, trái.
 */
export function buildIsoRhombus(
  center: MapPoint,
  halfW: number,
  halfD: number,
): MapPoint[] {
  const [cx, cy] = center;
  const p0 = projectIso([cx - halfW, cy - halfD]); // sau
  const p1 = projectIso([cx + halfW, cy - halfD]); // phải
  const p2 = projectIso([cx + halfW, cy + halfD]); // trước
  const p3 = projectIso([cx - halfW, cy + halfD]); // trái
  return [p0, p1, p2, p3];
}

/**
 * Khối hộp đặc, trả về 3 mặt nhìn thấy được. height > 0 nhô lên, height < 0 chìm xuống.
 */
export function buildIsoBox(
  center: MapPoint,
  halfW: number,
  halfD: number,
  height: number,
): IsoBoxFaces {
  const [p0, p1, p2, p3] = buildIsoRhombus(center, halfW, halfD);

  if (height >= 0) {
    const topP0 = lift(p0, height);
    const topP1 = lift(p1, height);
    const topP2 = lift(p2, height);
    const topP3 = lift(p3, height);

    return {
      top: [topP0, topP1, topP2, topP3],
      left: [p2, p3, topP3, topP2],
      right: [p1, p2, topP2, topP1],
    };
  }

  // height < 0: tấm sàn/chìm xuống, mặt trên ở cao độ sàn, đáy hạ xuống
  const botP1 = lift(p1, height); // height âm nên lift trừ số âm -> tăng Y
  const botP2 = lift(p2, height);
  const botP3 = lift(p3, height);

  return {
    top: [p0, p1, p2, p3],
    left: [p2, p3, botP3, botP2],
    right: [p1, p2, botP2, botP1],
  };
}

/**
 * Mặt phẳng nghiêng cho đường dốc, cạnh sau nâng lên `rise`.
 */
export function buildIsoRamp(
  center: MapPoint,
  halfW: number,
  halfD: number,
  rise: number,
): IsoRampFaces {
  const [p0, p1, p2, p3] = buildIsoRhombus(center, halfW, halfD);
  const backLeft = lift(p0, rise);
  const backRight = lift(p1, rise);
  const frontCenter: MapPoint = [
    (p3[0] + p2[0]) / 2,
    (p3[1] + p2[1]) / 2,
  ];
  const backCenter: MapPoint = [
    (backLeft[0] + backRight[0]) / 2,
    (backLeft[1] + backRight[1]) / 2,
  ];

  return {
    deck: [backLeft, backRight, p2, p3],
    left: [p3, p0, backLeft],
    right: [p1, p2, backRight],
    // Lối xuống cần một miệng hầm thẳng đứng ở đầu thấp để không trông
    // giống một tấm sàn bị kéo lệch xuống dưới.
    opening: rise < 0 ? [p0, p1, backRight, backLeft] : null,
    // Các vạch chạy dọc theo hướng di chuyển của xe, từ đầu gần đến đầu xa.
    centerLine: [frontCenter, backCenter],
    sideLines: [
      [p3, backLeft],
      [p2, backRight],
    ],
    direction: rise < 0 ? "DOWN" : "UP",
  };
}

/**
 * Nở một đoạn thẳng SONG SONG VỚI TRỤC trong không gian nguồn thành dải rộng
 * `width`, rồi chiếu thành tứ giác. Ném lỗi nếu đoạn không song song trục.
 */
export function buildIsoRibbon(
  from: MapPoint,
  to: MapPoint,
  width: number,
): MapPoint[] {
  const [x1, y1] = from;
  const [x2, y2] = to;

  const isHorizontal = y1 === y2 && x1 !== x2;
  const isVertical = x1 === x2 && y1 !== y2;

  if (!isHorizontal && !isVertical) {
    throw new Error(
      `Đoạn thẳng từ [${x1}, ${y1}] đến [${x2}, ${y2}] không song song với trục toạ độ.`,
    );
  }

  const halfWidth = width / 2;

  if (isHorizontal) {
    const minX = Math.min(x1, x2);
    const maxX = Math.max(x1, x2);
    return [
      projectIso([minX, y1 - halfWidth]),
      projectIso([maxX, y1 - halfWidth]),
      projectIso([maxX, y1 + halfWidth]),
      projectIso([minX, y1 + halfWidth]),
    ];
  }

  const minY = Math.min(y1, y2);
  const maxY = Math.max(y1, y2);
  return [
    projectIso([x1 - halfWidth, minY]),
    projectIso([x1 + halfWidth, minY]),
    projectIso([x1 + halfWidth, maxY]),
    projectIso([x1 - halfWidth, maxY]),
  ];
}

/**
 * Nở cả polyline thành mảng tứ giác, mỗi đoạn một tứ giác.
 */
export function buildIsoRibbonPath(
  points: MapPoint[],
  width: number,
): MapPoint[][] {
  if (points.length < 2) return [];

  const quads: MapPoint[][] = [];
  for (let i = 0; i < points.length - 1; i += 1) {
    quads.push(buildIsoRibbon(points[i], points[i + 1], width));
  }
  return quads;
}

/**
 * Đổi toạ độ viewBox isometric sang phần trăm khung, dùng cho lớp HTML.
 */
export function toIsoPercent(point: MapPoint): MapPoint {
  return [(point[0] / ISO_VIEW_W) * 100, (point[1] / ISO_VIEW_H) * 100];
}

/**
 * Đổi mảng điểm thành chuỗi cho thuộc tính `points` của <polygon> và <polyline>.
 */
export function pointsToPolygon(points: MapPoint[]): string {
  return points.map(([x, y]) => `${x},${y}`).join(" ");
}
