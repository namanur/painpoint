"""
Integration tests for the full Validation Pipeline (Stages 1.4 & 2.4).
Requires a running PostgreSQL instance.
"""

import pytest
import json
import asyncio
from src.pipeline.validation import ValidationPipeline, PipelineError
from src.validators.syntax_parser import CompilationError
from src.validators.business_rules import BusinessRuleViolation


TEST_DATABASE_URL = "postgresql://localhost:5432/painpoint_test"


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def pool():
    try:
        import asyncpg
        pool = await asyncpg.create_pool(
            TEST_DATABASE_URL,
            min_size=1,
            max_size=5,
        )
        
        # Initialize schema
        from src.db.schema import init_db
        await init_db(pool)
        
        yield pool
        
        await pool.close()
    except Exception as e:
        pytest.skip(f"Database not available: {e}")


@pytest.fixture
def pipeline(pool):
    return ValidationPipeline(pool)


@pytest.mark.asyncio
async def test_validate_contract_pipeline_valid():
    """Test Levels 0-3 without database."""
    raw_json = '''{
        "role": "A test assistant for pipeline validation",
        "allowed_tools": ["mcp_read"],
        "forbidden_actions": [],
        "max_retries": 2
    }'''
    
    from src.pipeline.validation import validate_contract_pipeline
    contract = validate_contract_pipeline(raw_json)
    assert contract.max_retries == 2


@pytest.mark.asyncio
async def test_validate_contract_pipeline_invalid_json():
    """Test Level 1 failure in pipeline."""
    from src.pipeline.validation import validate_contract_pipeline
    with pytest.raises(CompilationError, match="Level 1 Failure"):
        validate_contract_pipeline('{invalid json}')


@pytest.mark.asyncio
async def test_validate_contract_pipeline_dangerous_no_approval():
    """Test Level 3 failure in pipeline."""
    raw_json = '''{
        "role": "A database admin for testing",
        "allowed_tools": ["mcp_database_write"]
    }'''
    from src.pipeline.validation import validate_contract_pipeline
    with pytest.raises(BusinessRuleViolation, match="Level 3 Failure"):
        validate_contract_pipeline(raw_json)


# Database-required tests below
@pytest.mark.asyncio
async def test_compile_and_save_safe_contract(pool, pipeline):
    """Test full pipeline with safe contract -> PENDING status."""
    workflow_id = await pipeline.save_workflow(name="Safe Contract Test")
    
    raw_llm = '''{
        "role": "A safe reading assistant for testing purposes",
        "allowed_tools": ["mcp_read"],
        "forbidden_actions": ["delete"],
        "max_retries": 2
    }'''
    
    node_id, status = await pipeline.compile_and_save_contract(
        raw_llm_output=raw_llm,
        workflow_id=workflow_id,
    )
    
    assert node_id is not None
    assert status == "PENDING"  # Safe contract -> PENDING


@pytest.mark.asyncio
async def test_compile_and_save_dangerous_contract(pool, pipeline):
    """Test full pipeline with dangerous contract -> AWAITING_APPROVAL."""
    workflow_id = await pipeline.save_workflow(name="Dangerous Contract Test")
    
    raw_llm = '''{
        "role": "A payment processor for handling charges",
        "allowed_tools": ["mcp_stripe_charge"],
        "forbidden_actions": [],
        "max_retries": 1
    }'''
    
    node_id, status = await pipeline.compile_and_save_contract(
        raw_llm_output=raw_llm,
        workflow_id=workflow_id,
    )
    
    assert node_id is not None
    assert status == "AWAITING_APPROVAL"  # Dangerous -> AWAITING_APPROVAL


@pytest.mark.asyncio
async def test_compile_and_save_fails_level1(pool, pipeline):
    """Test pipeline rejects invalid JSON (Level 1 failure)."""
    workflow_id = await pipeline.save_workflow(name="Level1 Fail Test")
    
    with pytest.raises(CompilationError):
        await pipeline.compile_and_save_contract(
            raw_llm_output='{invalid json',
            workflow_id=workflow_id,
        )


@pytest.mark.asyncio
async def test_compile_and_save_fails_level3(pool, pipeline):
    """Test pipeline rejects dangerous tools without approval (Level 3)."""
    workflow_id = await pipeline.save_workflow(name="Level3 Fail Test")
    
    raw_llm = '''{
        "role": "Database admin without approval tool",
        "allowed_tools": ["mcp_database_write"]
    }'''
    
    with pytest.raises(BusinessRuleViolation):
        await pipeline.compile_and_save_contract(
            raw_llm_output=raw_llm,
            workflow_id=workflow_id,
        )


@pytest.mark.asyncio
async def test_markdown_wrapped_llm_output(pool, pipeline):
    """Test that markdown-wrapped JSON is handled correctly."""
    workflow_id = await pipeline.save_workflow(name="Markdown Test")
    
    raw_llm = '''```json
    {
        "role": "A markdown wrapped assistant for testing",
        "allowed_tools": ["mcp_read"],
        "max_retries": 1
    }
    ```'''
    
    node_id, status = await pipeline.compile_and_save_contract(
        raw_llm_output=raw_llm,
        workflow_id=workflow_id,
    )
    
    assert node_id is not None
    assert status == "PENDING"


@pytest.mark.asyncio
async def test_verify_saved_contract_in_db(pool, pipeline):
    """Test that saved contract can be retrieved from DB."""
    workflow_id = await pipeline.save_workflow(name="Verify DB Test")
    
    raw_llm = '''{
        "role": "A verification assistant for database testing",
        "allowed_tools": ["mcp_read", "mcp_search"],
        "forbidden_actions": ["delete_all"],
        "max_retries": 3
    }'''
    
    node_id, _ = await pipeline.compile_and_save_contract(
        raw_llm_output=raw_llm,
        workflow_id=workflow_id,
    )
    
    # Retrieve and verify
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT prompt_contract FROM nodes WHERE id = $1::UUID",
            node_id,
        )
        stored = json.loads(row['prompt_contract'])
        assert stored['role'] == "A verification assistant for database testing"
        assert stored['max_retries'] == 3
        assert "mcp_read" in stored['allowed_tools']
