job "modarchitect-execution" {
  datacenters = ["sws-core-ha"]
  type = "service"
  group "execution" {
    count = 1
    constraint {
      attribute = "${node.unique.name}"
      value = "SR850"
    }
    update {
      max_parallel = 1
      min_healthy_time = "10s"
      healthy_deadline = "5m"
      progress_deadline = "10m"
      auto_revert = true
    }
    network {
      mode = "host"
      port "http" { static = 18926 }
    }
    service {
      name = "modarchitect-execution"
      port = "http"
      provider = "consul"
      check {
        type = "http"
        path = "/health"
        interval = "10s"
        timeout = "3s"
      }
    }
    task "worker" {
      driver = "docker"
      user = "0"
      config {
        image = "172.16.1.122/sumfen/modarchitect-api:0.1.1-20261116-570beac9e18b@sha256:bf8d47b82c7577993f9f6028700f18c0d93f9fe2b66749a9e5ac86cb851e299c"
        network_mode = "host"
        dns_servers = ["${attr.unique.network.ip-address}"]
        command = "python"
        args = ["-m", "uvicorn", "modarchitect.runtime.worker:app", "--host", "0.0.0.0", "--port", "18926"]
        volumes = ["/var/run/docker.sock:/var/run/docker.sock"]
      }
      env {
        MODARCHITECT_RUNTIME_PROFILES = "/local/runtime-profiles.json"
        TZ = "Asia/Shanghai"
      }
      template {
        data = <<EOH
{{ with nomadVar "nomad/jobs/modarchitect-execution" }}
MODARCHITECT_DS_URL={{ .ds_url | toJSON }}
MODARCHITECT_DS_TOKEN={{ .ds_token | toJSON }}
MODARCHITECT_DS_PROJECT={{ .ds_project | toJSON }}
MODARCHITECT_DS_WORKFLOW={{ .ds_workflow | toJSON }}
MODARCHITECT_DS_SOURCE_WORKFLOW={{ .ds_source_workflow | toJSON }}
MODARCHITECT_DS_TENANT={{ .ds_tenant | toJSON }}
MODARCHITECT_DS_SOURCE_ENVIRONMENT_NAME={{ .source_environment_name | toJSON }}
MODARCHITECT_WEATHER_ACCESS={{ .weather_access | toJSON }}
MODARCHITECT_WORKER_KEY={{ .worker_key | toJSON }}
MODARCHITECT_INTERNAL_API={{ .internal_api | toJSON }}
{{ end }}
EOH
        destination = "secrets/execution.env"
        env = true
        perms = "0400"
        change_mode = "restart"
      }
      template {
        data = <<EOH
{
  "catalog_weather_conditions@1": {
    "image": "sha256:0d64d6dd35cda97b29e3f690d5755ad2ad43931cee3e992285e201b2fde5ff1c",
    "outputs": [
      "report",
      "series"
    ],
    "manifest_digest": "sha256:d79651fa4b49135b1c273adf375dfaefac4bad9628f7a405b8856b59311a5302",
    "memory_bytes": 536870912
  },
  "random_forest_training@1": {
    "image": "sha256:0b191c51ae154df8ecce64d7997b6d0415b7f491b8b50c48b6bc790adcb34d8d",
    "outputs": [
      "trained_model",
      "predictions"
    ],
    "manifest_digest": "sha256:475992ec89e0158fbd24d2919cf75f45171f0c6f8f9fad97805f0cbc7bceb871",
    "memory_bytes": 536870912,
    "state_output": "trained_model",
    "inference": "random_forest_predict@1"
  },
  "random_forest_predict@1": {
    "image": "sha256:f464fd9868ea0c6f26d0b3d49a5624114d333ad00c6b14c83af884e5e402d2b9",
    "outputs": [
      "predictions"
    ],
    "manifest_digest": "sha256:3a31bf161ce2f6030f3758735216428ea4ab8a6e1be694bc158bd11e8e77d00f",
    "memory_bytes": 536870912
  },
  "xgboost_training@1": {
    "image": "sha256:70f057703ff67018608c7f9c2cddfb18ad0a66c353847672511e72222f83c4a9",
    "outputs": [
      "trained_model",
      "predictions"
    ],
    "manifest_digest": "sha256:65fe8f89ebe66a2438af7e378d149a51d333cb86633ddc9a6b50d4d739ecf2a7",
    "memory_bytes": 536870912,
    "state_output": "trained_model",
    "inference": "xgboost_predict@1"
  },
  "xgboost_predict@1": {
    "image": "sha256:c0b42e0e95290b27c12184675f59727b71a4d4fcdfc771fce42a950d0d8751ee",
    "outputs": [
      "predictions"
    ],
    "manifest_digest": "sha256:6c54c29ea7723b458754277c8e535a69a7f6f12328623048f11c177ff564e5cd",
    "memory_bytes": 536870912
  },
  "gaussian_process_training@1": {
    "image": "sha256:1f1925391f66beab915526636f3a34aeaa1a1c3dfea73bf7fabfb80eb14ba0bc",
    "outputs": [
      "trained_model",
      "predictions"
    ],
    "manifest_digest": "sha256:7639fb79544cece6094a12e4d6c9de854f64802ff3c9f27d3e2462fcab1be4ef",
    "memory_bytes": 536870912,
    "state_output": "trained_model",
    "inference": "gaussian_process_predict@1"
  },
  "gaussian_process_predict@1": {
    "image": "sha256:52abecf408abf1a25ba110923114369bee54a022101d0d03bd2c052ff89c8e0c",
    "outputs": [
      "predictions"
    ],
    "manifest_digest": "sha256:7ad7fa090c2cc3810de09d95822e047f6c31e9f1c9d745b1638e0a624789dce4",
    "memory_bytes": 536870912
  },
  "multivariate_linear_training@1": {
    "image": "sha256:3fc497670ac1229160deb4c39106aea1ca53106d41ba2235e7ebd2c51246758f",
    "outputs": [
      "trained_model",
      "predictions"
    ],
    "manifest_digest": "sha256:b2b89276d513b3a345115e2263e59102ddbc693a4b6eaccfa2760e9254a874f2",
    "memory_bytes": 536870912,
    "state_output": "trained_model",
    "inference": "multivariate_linear_predict@1"
  },
  "multivariate_linear_predict@1": {
    "image": "sha256:ad41c3904f10c3e4cf0612065d41e0e3a5b62ebcb0714a11f0dd9f10ef3f1a2d",
    "outputs": [
      "predictions"
    ],
    "manifest_digest": "sha256:2048c860ca7ed390897a6cb4d48d4d8beaf67eeac9fc803f31aff1c80b088958",
    "memory_bytes": 536870912
  }
}
EOH
        destination = "local/runtime-profiles.json"
        perms = "0444"
        change_mode = "restart"
      }
      resources {
        cpu = 1000
        memory = 768
      }
    }
    task "dispatcher" {
      driver = "docker"
      config {
        image = "172.16.1.122/sumfen/modarchitect-api:0.1.1-20261116-570beac9e18b@sha256:bf8d47b82c7577993f9f6028700f18c0d93f9fe2b66749a9e5ac86cb851e299c"
        network_mode = "host"
        dns_servers = ["${attr.unique.network.ip-address}"]
        command = "python"
        args = ["-m", "modarchitect.runtime.scheduler"]
      }
      env { TZ = "Asia/Shanghai" }
      template {
        data = <<EOH
{{ with nomadVar "nomad/jobs/modarchitect-execution" }}
MODARCHITECT_DS_URL={{ .ds_url | toJSON }}
MODARCHITECT_DS_TOKEN={{ .ds_token | toJSON }}
MODARCHITECT_DS_PROJECT={{ .ds_project | toJSON }}
MODARCHITECT_DS_WORKFLOW={{ .ds_workflow | toJSON }}
MODARCHITECT_DS_SOURCE_WORKFLOW={{ .ds_source_workflow | toJSON }}
MODARCHITECT_DS_TENANT={{ .ds_tenant | toJSON }}
MODARCHITECT_DS_SOURCE_ENVIRONMENT_NAME={{ .source_environment_name | toJSON }}
MODARCHITECT_WORKER_KEY={{ .worker_key | toJSON }}
MODARCHITECT_INTERNAL_API={{ .internal_api | toJSON }}
{{ end }}
EOH
        destination = "secrets/dispatcher.env"
        env = true
        perms = "0400"
        change_mode = "restart"
      }
      resources {
        cpu = 100
        memory = 256
      }
    }
  }
}
