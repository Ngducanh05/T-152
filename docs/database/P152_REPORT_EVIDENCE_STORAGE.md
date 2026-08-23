# Wrong-Parking Report Evidence Storage

Create a private Supabase Storage bucket before enabling production report evidence uploads:

- Bucket name: `wrong-parking-evidence` unless `SUPABASE_REPORT_EVIDENCE_BUCKET` is overridden.
- Public access: disabled.
- Upload/read/delete access: backend only, using `SUPABASE_SERVICE_ROLE_KEY`.
- Browser clients must not receive the service-role key and must not choose object paths.

The image is optional. The FastAPI backend uploads at most one image per report to a
backend-generated path and gives admins five-minute signed URLs for review. A report without
an image follows the same verification and reward lifecycle.
