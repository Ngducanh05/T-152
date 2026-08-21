# Wrong-Parking Report Evidence Storage

Create a private Supabase Storage bucket before enabling production report evidence uploads:

- Bucket name: `wrong-parking-evidence` unless `SUPABASE_REPORT_EVIDENCE_BUCKET` is overridden.
- Public access: disabled.
- Upload/read/delete access: backend only, using `SUPABASE_SERVICE_ROLE_KEY`.
- Browser clients must not receive the service-role key and must not choose object paths.

The FastAPI backend uploads one image per report to a backend-generated path and gives admins short-lived signed URLs for review.
