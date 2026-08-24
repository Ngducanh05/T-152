import type { Metadata } from "next";
import Link from "next/link";

import {
  buildPrivacyContactMailtoUri,
  getPrivacyContactEmail,
} from "@/lib/public-config";

import styles from "./privacy.module.css";

export const metadata: Metadata = {
  title: "Quyền riêng tư | ParkSmart AI",
  description:
    "Thông tin về dữ liệu wrong-parking report, quyền truy cập, thời gian lưu giữ và cách yêu cầu xóa dữ liệu trong ParkSmart AI public beta.",
};

export default function PrivacyPage() {
  const contactEmail = getPrivacyContactEmail();
  const contactMailtoUri = buildPrivacyContactMailtoUri(
    contactEmail ?? undefined,
  );

  return (
    <main className={styles.page}>
      <article className={styles.policy}>
        <header>
          <p className={styles.eyebrow}>PARKSMART AI PUBLIC BETA</p>
          <h1>Quyền riêng tư khi gửi báo cáo đỗ sai</h1>
          <p>
            ParkSmart AI public beta phục vụ thử nghiệm sản phẩm, không phải hệ
            thống vận hành bãi xe 24/7. Nội dung dưới đây mô tả cách dữ liệu của
            báo cáo đỗ sai được xử lý trong phiên bản hiện tại.
          </p>
        </header>

        <section aria-labelledby="privacy-data">
          <h2 id="privacy-data">Dữ liệu có thể được thu thập</h2>
          <ul>
            <li>Ảnh hiện trường do bạn tùy chọn cung cấp.</li>
            <li>Biển số quan sát được và mô tả, đều là thông tin tùy chọn.</li>
            <li>Tài khoản gửi báo cáo, ô đỗ liên quan và thời gian gửi.</li>
          </ul>
        </section>

        <section aria-labelledby="privacy-purpose">
          <h2 id="privacy-purpose">Mục đích sử dụng</h2>
          <p>Dữ liệu được dùng để:</p>
          <ul>
            <li>Xác minh báo cáo và hỗ trợ admin xử lý vi phạm.</li>
            <li>Xử lý reward ParkSmart theo chính sách hiện hành.</li>
            <li>Phát hiện spam hoặc báo cáo trùng.</li>
          </ul>
        </section>

        <section aria-labelledby="privacy-access">
          <h2 id="privacy-access">Ai có thể truy cập ảnh</h2>
          <p>
            Ảnh được lưu trong private Storage bucket. Browser và người dùng
            thông thường không có service-role key. Chỉ admin được ủy quyền mới
            có thể xem ảnh thông qua signed URL có thời hạn.
          </p>
        </section>

        <section aria-labelledby="privacy-retention">
          <h2 id="privacy-retention">Thời gian lưu giữ và hard-delete</h2>
          <p>
            Dữ liệu báo cáo và ảnh được giữ cho đến khi admin hard-delete báo cáo
            hoặc một yêu cầu xóa hợp lệ được xử lý. Hard-delete xóa bản ghi báo
            cáo và yêu cầu xóa Storage object tương ứng. Nếu Storage cleanup thất
            bại, hệ thống ghi cảnh báo để quản trị viên xử lý object còn sót.
          </p>
          <p>
            Reward ledger có thể được giữ để bảo toàn lịch sử điểm, nhưng sau
            hard-delete không chứa ảnh, biển số, mô tả hoặc đường dẫn ảnh của báo
            cáo đã xóa.
          </p>
        </section>

        <section aria-labelledby="privacy-deletion">
          <h2 id="privacy-deletion">Yêu cầu xóa dữ liệu</h2>
          {contactEmail && contactMailtoUri ? (
            <p>
              Gửi yêu cầu tới{" "}
              <a href={contactMailtoUri}>{contactEmail}</a>, kèm email
              tài khoản và report ID nếu bạn có.
            </p>
          ) : (
            <p className={styles.contactFallback}>
              Kênh liên hệ đang được cấu hình
            </p>
          )}
          <p>
            Không gửi mật khẩu, access token, API key hoặc bất kỳ secret nào
            trong yêu cầu hỗ trợ.
          </p>
        </section>

        <footer>
          <Link href="/login">Quay lại ParkSmart AI</Link>
        </footer>
      </article>
    </main>
  );
}
