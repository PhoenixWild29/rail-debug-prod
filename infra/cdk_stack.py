from aws_cdk import (
    Stack,
    App,
    aws_ecs as ecs,
    aws_ecr as ecr,
    aws_ec2 as ec2,
    aws_ecs_patterns as ecs_patterns,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct


class RailDebugStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, repo_name: str = "rail-debug", container_port: int = 8000, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # VPC and Cluster
        vpc = ec2.Vpc(self, "Vpc", max_azs=2)
        cluster = ecs.Cluster(self, "Cluster", vpc=vpc)

        # ECR Repo for Docker Image (use existing or create new)
        repo = ecr.Repository(self, "Repo", repository_name=repo_name)

        # Secrets Manager
        weaviate_secret = secretsmanager.Secret.from_secret_name_v2(self, "WeaviateSecret", "rail-debug/weaviate")
        openai_secret = secretsmanager.Secret.from_secret_name_v2(self, "OpenaiSecret", "rail-debug/openai")

        # Task definition and service
        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "Service",
            cluster=cluster,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_ecr_repository(repo),
                container_port=container_port,
                secrets={
                    "WEAVIATE_URL": ecs.Secret.from_secrets_manager(weaviate_secret, "url"),
                    "WEAVIATE_API_KEY": ecs.Secret.from_secrets_manager(weaviate_secret, "api_key"),
                    "OPENAI_API_KEY": ecs.Secret.from_secrets_manager(openai_secret, "api_key"),
                },
            ),
            desired_count=1,
            public_load_balancer=True,
        )

        # Permissions for pulling from ECR already granted; add more if needed
        service.task_definition.task_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryReadOnly")
        )

        # Autoscaling
        scalable_target = service.service.auto_scale_task_count(min_capacity=1, max_capacity=10)
        scalable_target.scale_on_cpu_utilization("CpuScaling", target_utilization_percent=70)
        scalable_target.scale_on_memory_utilization("MemoryScaling", target_utilization_percent=80)


app = App()
RailDebugStack(app, "RailDebugStack")
app.synth()
