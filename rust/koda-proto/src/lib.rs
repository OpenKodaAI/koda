pub mod common {
    pub mod v1 {
        tonic::include_proto!("koda.common.v1");
    }
}

pub mod runtime {
    pub mod v1 {
        tonic::include_proto!("koda.runtime.v1");
    }
}

pub mod retrieval {
    pub mod v1 {
        tonic::include_proto!("koda.retrieval.v1");
    }
}

pub mod memory {
    pub mod v1 {
        tonic::include_proto!("koda.memory.v1");
    }
}

pub mod artifact {
    pub mod v1 {
        tonic::include_proto!("koda.artifact.v1");
    }
}

pub mod security {
    pub mod v1 {
        tonic::include_proto!("koda.security.v1");
    }
}

pub mod bot_gateway {
    pub mod v1 {
        tonic::include_proto!("koda.bot_gateway.v1");
    }
}

pub mod policy_engine {
    pub mod v1 {
        tonic::include_proto!("koda.policy_engine.v1");
    }
}
