# Deploy path review checklist

- [x] Make SSH deploy idempotent regardless of branch state
- [ ] Add post-deploy health/version verification
- [ ] Add rollback path for failed deploys
- [ ] Ensure .env/secrets never enter Docker build context
- [ ] Add deploy dry-run/sanity check
