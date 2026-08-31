# Wrong-Parking Report Evidence Storage

Create a private Supabase Storage bucket before enabling production report evidence uploads:

- Bucket name: `wrong-parking-evidence` unless `SUPABASE_REPORT_EVIDENCE_BUCKET` is overridden.
- Public access: disabled.
- Upload/read/delete access: backend only, using `SUPABASE_SERVICE_ROLE_KEY`.
- Browser clients must not receive the service-role key and must not choose object paths.

The image is optional. The FastAPI backend uploads at most one image per report to a
backend-generated path and gives admins five-minute signed URLs for review. A report without
an image follows the same verification and reward lifecycle.

The user UI must not upload merely because a reason was selected. It first reveals the
optional plate, description and image fields, then sends the report only after the explicit
submit action. The modal keeps its action reachable through an internal scroll region and a
sticky submit dock on short viewports.

Admin evidence access remains tied to report authorization and uses a short-lived signed
URL. Hard-delete removes the Storage object together with the report row; any retained
reward-ledger source reference must not copy the image path, plate number or description
into reward metadata.

## Adjacent observation evidence

The same private bucket also stores `slot-observations/{observation_id}/...` objects. One optional
image uses the same backend-only MIME/signature/size validation as report evidence. The database
stores only nullable path, content type and byte count. No public URL is created: an admin requests
a five-minute signed URL through the admin-only observation endpoint when they explicitly choose to
view the proof. If the authoritative database mutation loses a race after upload, the backend makes
a best-effort delete of the orphaned private object.
