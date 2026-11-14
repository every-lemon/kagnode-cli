use anyhow::{Result, bail, ensure};
use argon2::{Argon2, PasswordHash, PasswordHasher, PasswordVerifier, password_hash::SaltString};
use sha2::{Digest, Sha256};
pub fn random() -> Result<String> {
    let mut value = [0; 32];
    getrandom::fill(&mut value).map_err(|_| anyhow::anyhow!("OS randomness unavailable"))?;
    Ok(hex::encode(value))
}
pub fn digest(value: &str) -> String {
    hex::encode(Sha256::digest(value.as_bytes()))
}
pub fn hash_password(password: &str) -> Result<String> {
    ensure!(
        (12..=1024).contains(&password.len()),
        "Use a password between 12 and 1024 bytes"
    );
    let mut salt = [0; 16];
    getrandom::fill(&mut salt).map_err(|_| anyhow::anyhow!("OS randomness unavailable"))?;
    let salt =
        SaltString::encode_b64(&salt).map_err(|_| anyhow::anyhow!("Salt encoding failed"))?;
    Argon2::default()
        .hash_password(password.as_bytes(), &salt)
        .map(|p| p.to_string())
        .map_err(|_| anyhow::anyhow!("Password hashing failed"))
}
pub fn verify(password: &str, hash: &str) -> bool {
    password.len() <= 1024
        && PasswordHash::new(hash).is_ok_and(|h| {
            Argon2::default()
                .verify_password(password.as_bytes(), &h)
                .is_ok()
        })
}
pub fn email(value: &str) -> Result<String> {
    let value = value.trim().to_lowercase();
    if value.len() > 254
        || value.chars().any(char::is_control)
        || !value.contains('@')
        || value.contains(char::is_whitespace)
    {
        bail!("Enter a valid administrator email");
    }
    Ok(value)
}
pub fn now() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64
}
