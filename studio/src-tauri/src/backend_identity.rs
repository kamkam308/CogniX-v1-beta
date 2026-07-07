pub(crate) fn is_supported_backend_service(service: &str) -> bool {
    matches!(service, "CogniX Backend" | "Unsloth UI Backend")
}

#[cfg(test)]
mod tests {
    use super::is_supported_backend_service;

    #[test]
    fn accepts_cognix_and_legacy_backend_names() {
        assert!(is_supported_backend_service("CogniX Backend"));
        assert!(is_supported_backend_service("Unsloth UI Backend"));
        assert!(!is_supported_backend_service("Other Backend"));
    }
}
