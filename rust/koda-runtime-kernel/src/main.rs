use anyhow::Result;
use koda_observability::init_tracing;
use koda_runtime_kernel::{serve, KernelConfig, RuntimeKernelServer};

#[tokio::main]
async fn main() -> Result<()> {
    init_tracing("koda-runtime-kernel");
    let target = std::env::var("RUNTIME_KERNEL_SOCKET")
        .unwrap_or_else(|_| "/tmp/koda-runtime/default/rpc/runtime-kernel.sock".into());
    let server = RuntimeKernelServer::new(KernelConfig::from_env());
    serve(&target, server).await
}
