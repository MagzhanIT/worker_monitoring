# Security

Status: token auth, bcrypt hashes, protected media and path validation are **implemented**; external penetration testing is **not performed**.

Admin creation requires explicit environment credentials. Access tokens are signed and time-limited. CORS is environment-controlled. Media identifiers resolve only inside approved roots. RTSP user information is redacted from logs and API responses. Production deployments require a unique secret, TLS reverse proxy, restricted filesystem permissions and rotated credentials.

