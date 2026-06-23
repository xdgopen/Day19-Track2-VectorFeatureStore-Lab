"""Five-query demonstration for the HybridMemoryAgent."""
from agent import HybridMemoryAgent


def main() -> None:
    agent = HybridMemoryAgent()
    agent.remember("Tôi đã đọc tài liệu Kubernetes về autoscaling HPA, cluster autoscaler và giới hạn tài nguyên.")
    agent.remember("Ghi chú cloud security: IAM least privilege, quản lý secrets, mã hóa dữ liệu và audit log.")
    agent.remember("Tài liệu về hạ tầng co giãn tự động theo lưu lượng, dùng load balancer và metrics CPU.")
    agent.remember("Tôi muốn học cloud-native, Kubernetes, bảo mật đám mây và tối ưu chi phí vận hành.")

    queries = [
        "Tôi đã đọc gì về Kubernetes?",
        "Recommend đọc gì tiếp",
        "Tôi đang quan tâm gì gần đây?",
        "Tài liệu về tự động mở rộng hạ tầng?",
        "Cho tôi summary cloud security",
    ]
    for number, query in enumerate(queries, start=1):
        print(f"\n{'=' * 72}\nDemo {number}: {query}\n{agent.recall(query)}")


if __name__ == "__main__":
    main()
