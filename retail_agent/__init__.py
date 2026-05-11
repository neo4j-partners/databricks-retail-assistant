"""Databricks Python wheel task entry points."""


def _raise_on_failure(status: int | None) -> None:
    if status not in (None, 0):
        raise RuntimeError(f"Entry point failed with status {status}")


def retail_graph_concierge_deploy() -> None:
    from retail_agent.deployment.deploy_agent import main

    _raise_on_failure(main())


def retail_graph_concierge_load_products() -> None:
    from retail_agent.deployment.load_products import load_sample_data

    load_sample_data()


def retail_graph_concierge_load_graphrag() -> None:
    from retail_agent.deployment.load_graphrag import main

    _raise_on_failure(main())


def retail_graph_concierge_demo() -> None:
    from retail_agent.demos.demo_agent import check_endpoint

    check_endpoint()


def retail_graph_concierge_demo_retrievers() -> None:
    from retail_agent.demos.demo_retrievers import demo_retrievers

    demo_retrievers()


def retail_graph_concierge_check_knowledge() -> None:
    from retail_agent.demos.check_knowledge import check_knowledge

    check_knowledge()


def retail_graph_concierge_deploy_supervisor() -> None:
    from retail_agent.deployment.deploy_supervisor import main

    _raise_on_failure(main())
