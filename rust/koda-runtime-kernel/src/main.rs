use anyhow::{Context, Result};
use koda_observability::init_tracing;
use koda_runtime_kernel::process_hygiene::harden_current_process;
use koda_runtime_kernel::{serve, KernelConfig, RuntimeKernelServer};

fn main() -> Result<()> {
    // First, before the async runtime, tracing or any env read (ADR-002 §2.4
    // L1, AG-04): the workers and commands this kernel starts share its uid,
    // so it must be non-dumpable and write no core. Refuse to run otherwise.
    harden_current_process().context("cannot harden the runtime kernel process")?;
    tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .context("cannot build the tokio runtime")?
        .block_on(run())
}

async fn run() -> Result<()> {
    init_tracing("koda-runtime-kernel");
    let target = std::env::var("RUNTIME_KERNEL_SOCKET")
        .unwrap_or_else(|_| "/tmp/koda-runtime/default/rpc/runtime-kernel.sock".into());
    let server = RuntimeKernelServer::new(KernelConfig::from_env());
    serve(&target, server).await
}
