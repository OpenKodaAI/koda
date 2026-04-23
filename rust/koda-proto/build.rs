fn main() -> Result<(), Box<dyn std::error::Error>> {
    let protoc = protoc_bin_vendored::protoc_bin_path()?;
    std::env::set_var("PROTOC", protoc);
    tonic_build::configure().compile_protos(
        &[
            "../../proto/common/v1/metadata.proto",
            "../../proto/runtime/v1/runtime.proto",
            "../../proto/retrieval/v1/retrieval.proto",
            "../../proto/memory/v1/memory.proto",
            "../../proto/artifact/v1/artifact.proto",
            "../../proto/security/v1/security.proto",
        ],
        &["../../proto"],
    )?;
    Ok(())
}
