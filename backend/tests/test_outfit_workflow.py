from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver

from app.outfit_workflow import OutfitAgentState, outfit_agent_graph, outfit_checkpointer, validation_route


def test_validation_route_completes_for_a_valid_answer():
    state = OutfitAgentState(guard={"status": "passed"})
    assert validation_route(state) == "complete"


def test_validation_route_falls_back_for_an_invalid_answer():
    state = OutfitAgentState(guard={"status": "failed"})
    assert validation_route(state) == "fallback"


def test_graph_has_persistent_checkpointer_and_image_generation_node():
    assert isinstance(outfit_checkpointer, PyMySQLSaver)
    assert "prepare_image_generation" in outfit_agent_graph.nodes
