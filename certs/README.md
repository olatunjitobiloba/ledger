# Rumpty database certificate

Save the server/CA certificate supplied by Rumpty in this directory. The
current deployment uses `ledger-db-ca.crt`; certificates are ignored by Git.

Set these values in `.env`:

```env
LEDGER_DB_SSLMODE=verify-full
LEDGER_DB_SSLROOTCERT=./certs/ledger-db-ca.crt
```

Use the internal connection string for services deployed on Rumpty. Use the
external connection string only from a local machine. If Rumpty's certificate
does not contain the host name you are connecting to, use the provider's
documented SSL mode rather than weakening verification on your own.
