"""
Unit tests for the vmap transform.

This module provides comprehensive testing for the vectorized mapping (vmap)
transformation in XCS, including basic functionality, edge cases, error handling,
and advanced usage patterns.
"""

import pytest
import threading
import time
from typing import Dict, Any, List, Callable, Set, Tuple

from ember.xcs.transforms import vmap
from ember.xcs.transforms.vmap import _get_batch_size, _prepare_batched_inputs, _combine_outputs

# Import test operators
from tests.unit.xcs.transforms.mock_operators import (
    BasicOperator,
    StatefulOperator,
    NestedOperator,
    ExceptionOperator,
    MockModule,
    ComplexInputOperator
)
from tests.unit.xcs.transforms.test_utils import (
    generate_batch_inputs,
    assert_processing_time
)


# =============================== Fixtures ===============================

@pytest.fixture
def basic_operator():
    """Fixture providing a basic operator instance."""
    return BasicOperator()


@pytest.fixture
def stateful_operator():
    """Fixture providing a stateful operator instance."""
    return StatefulOperator()


@pytest.fixture
def exception_operator():
    """Fixture providing an exception-raising operator."""
    return ExceptionOperator(fail_on_inputs=["fail_input"])


@pytest.fixture
def module_operator():
    """Fixture providing a Module-based operator instance."""
    return MockModule()


# =============================== Unit Tests for Internal Functions ===============================

class TestVMapInternals:
    """Unit tests for internal vmap functions."""
    
    def test_get_batch_size(self):
        """Test batch size detection from inputs."""
        # Case 1: Empty inputs
        assert _get_batch_size({}, 0) == 1
        
        # Case 2: Single axis for all inputs
        inputs = {"prompts": ["a", "b", "c"], "config": {"mode": "test"}}
        assert _get_batch_size(inputs, 0) == 3
        
        # Case 3: Dict of axes
        inputs = {"prompts": ["a", "b"], "other": ["x", "y"]}
        axes = {"prompts": 0, "other": 0}
        assert _get_batch_size(inputs, axes) == 2
        
        # Case 4: Inconsistent batch sizes should raise ValueError
        inputs = {"prompts": ["a", "b"], "other": ["x", "y", "z"]}
        axes = {"prompts": 0, "other": 0}
        with pytest.raises(ValueError, match="Inconsistent batch sizes"):
            _get_batch_size(inputs, axes)
        
        # Case 5: Empty list inputs
        inputs = {"prompts": []}
        # The actual implementation seems to return 0 for empty lists
        assert _get_batch_size(inputs, 0) == 0
    
    def test_prepare_batched_inputs(self):
        """Test preparation of batched inputs."""
        # Case 1: Simple input with single batch axis
        inputs = {"prompts": ["a", "b"]}
        result = _prepare_batched_inputs(inputs, 0, 2)
        assert result == {"prompts": ["a", "b"]}
        
        # Case 2: Mixed inputs with scalar values
        inputs = {"prompts": ["a", "b"], "config": {"mode": "test"}}
        result = _prepare_batched_inputs(inputs, 0, 2)
        assert result["prompts"] == ["a", "b"]
        assert result["config"] == [{"mode": "test"}, {"mode": "test"}]  # Replicated
        
        # Case 3: Dict of axes
        inputs = {"prompts": ["a", "b"], "config": {"mode": "test"}}
        axes = {"prompts": 0}  # Only batch prompts
        result = _prepare_batched_inputs(inputs, axes, 2)
        assert result["prompts"] == ["a", "b"]
        assert result["config"] == [{"mode": "test"}, {"mode": "test"}]
        
        # Case 4: Empty list handling
        inputs = {"prompts": []}
        result = _prepare_batched_inputs(inputs, 0, 2)
        assert result["prompts"] == [[]] * 2  # List of empty lists
    
    def test_combine_outputs(self):
        """Test combining of outputs from batched execution."""
        # Case 1: Empty results
        assert _combine_outputs([]) == {}
        
        # Case 2: Basic dictionary outputs
        results = [
            {"results": ["a_processed"]}, 
            {"results": ["b_processed"]}
        ]
        combined = _combine_outputs(results)
        assert combined == {"results": ["a_processed", "b_processed"]}
        
        # Case 3: Complex nested outputs
        results = [
            {"results": ["a_processed"], "metadata": {"id": 1}},
            {"results": ["b_processed"], "metadata": {"id": 2}}
        ]
        combined = _combine_outputs(results)
        assert combined["results"] == ["a_processed", "b_processed"]
        assert combined["metadata"] == [{"id": 1}, {"id": 2}]
        
        # Case 4: Non-dictionary outputs
        results = ["a", "b", "c"]
        combined = _combine_outputs(results)
        assert combined == {"result": ["a", "b", "c"]}
        
        # Case 5: Single-item list flattening
        results = [
            {"results": [["a_nested"]]},
            {"results": [["b_nested"]]}
        ]
        combined = _combine_outputs(results)
        # Convert to strings for comparison
        assert str(combined["results"][0]) == str(["a_nested"])
        assert str(combined["results"][1]) == str(["b_nested"])


# =============================== Main vmap Tests ===============================

class TestVMap:
    """Comprehensive tests for the vmap transformation."""
    
    def test_vmap_basic_functionality(self, basic_operator):
        """Test that vmap correctly vectorizes a basic operator."""
        vectorized_op = vmap(basic_operator)
        
        # Test with batch input
        batch_inputs = {
            "prompts": ["prompt1", "prompt2", "prompt3"]
        }
        
        result = vectorized_op(inputs=batch_inputs)
        assert "results" in result
        assert len(result["results"]) == 3
        assert result["results"] == ["prompt1_processed", "prompt2_processed", "prompt3_processed"]
        
        # Verify original operator was called for each batch item
        assert basic_operator.call_count == 3
    
    def test_vmap_with_empty_inputs(self, basic_operator):
        """Test vmap behavior with empty inputs."""
        vectorized_op = vmap(basic_operator)
        
        # Empty list
        result = vectorized_op(inputs={"prompts": []})
        assert "results" in result
        assert len(result["results"]) == 0
        
        # Missing key
        result = vectorized_op(inputs={})
        assert "results" in result
        assert len(result["results"]) == 0
    
    def test_vmap_with_single_item(self, basic_operator):
        """Test vmap with a single item (non-list input)."""
        vectorized_op = vmap(basic_operator)
        
        # Single scalar input
        result = vectorized_op(inputs={"prompts": "single_prompt"})
        assert "results" in result
        assert len(result["results"]) == 1
        assert result["results"] == ["single_prompt_processed"]
    
    def test_vmap_with_custom_axes(self, basic_operator):
        """Test vmap with custom input and output axes."""
        # Custom input axes
        in_axes = {"prompts": 0, "config": None}  # batch prompts, replicate config
        vectorized_op = vmap(basic_operator, in_axes=in_axes)
        
        batch_inputs = {
            "prompts": ["a", "b", "c"],
            "config": {"mode": "test"}
        }
        
        result = vectorized_op(inputs=batch_inputs)
        assert "results" in result
        assert len(result["results"]) == 3
    
    def test_vmap_with_function(self):
        """Test vmap with a function instead of an operator."""
        call_count = 0
        
        def process_fn(*, inputs):
            nonlocal call_count
            call_count += 1
            prompts = inputs.get("prompts", [])
            if isinstance(prompts, list):
                return {"results": [f"{p}_fn" for p in prompts]}
            return {"results": [f"{prompts}_fn"]}
        
        vectorized_fn = vmap(process_fn)
        
        # Test with batch input
        batch_inputs = {
            "prompts": ["a", "b", "c"]
        }
        
        result = vectorized_fn(inputs=batch_inputs)
        assert "results" in result
        assert len(result["results"]) == 3
        assert result["results"] == ["a_fn", "b_fn", "c_fn"]
        assert call_count == 3
    
    def test_vmap_with_stateful_operator(self, stateful_operator):
        """Test vmap with a stateful operator."""
        vectorized_op = vmap(stateful_operator)
        
        # First batch
        batch1 = {"prompts": ["s1", "s2"]}
        result1 = vectorized_op(inputs=batch1)
        
        assert result1["results"] == ["s1_processed", "s2_processed"]
        assert stateful_operator.history == ["s1_processed", "s2_processed"]
        
        # Second batch
        batch2 = {"prompts": ["s3", "s4"]}
        result2 = vectorized_op(inputs=batch2)
        
        assert result2["results"] == ["s3_processed", "s4_processed"]
        assert stateful_operator.history == ["s1_processed", "s2_processed", "s3_processed", "s4_processed"]
        
        # Verify order is preserved
        assert len(stateful_operator.history) == 4
        assert stateful_operator.history[0] == "s1_processed"
        assert stateful_operator.history[1] == "s2_processed"
        assert stateful_operator.history[2] == "s3_processed"
        assert stateful_operator.history[3] == "s4_processed"
    
    def test_vmap_with_nested_operator(self):
        """Test vmap with a nested operator structure."""
        op1 = BasicOperator(lambda x: f"{x}_first")
        op2 = BasicOperator(lambda x: f"{x}_second")
        nested_op = NestedOperator([op1, op2])
        
        vectorized_op = vmap(nested_op)
        
        batch_inputs = {"prompts": ["n1", "n2", "n3"]}
        result = vectorized_op(inputs=batch_inputs)
        
        expected = ["n1_first_second", "n2_first_second", "n3_first_second"]
        assert result["results"] == expected
        
        # Verify each operator was called 3 times
        assert op1.call_count == 3
        assert op2.call_count == 3
    
    def test_vmap_exception_handling(self, exception_operator):
        """Test vmap propagates exceptions properly."""
        vectorized_op = vmap(exception_operator)
        
        # Regular case - should succeed
        result = vectorized_op(inputs={"prompts": ["ok1", "ok2"]})
        assert result["results"] == ["ok1_success", "ok2_success"]
        
        # Case with failure - should propagate the exception
        with pytest.raises(Exception) as excinfo:
            vectorized_op(inputs={"prompts": ["ok1", "fail_input", "ok2"]})
        
        # Assert that the exception contains our expected message somewhere in the chain
        error_text = str(excinfo.value)
        assert "Failed on input" in error_text or "fail_input" in error_text
    
    def test_vmap_with_module_operator(self, module_operator):
        """Test vmap with a Module-based operator."""
        vectorized_op = vmap(module_operator)
        
        batch_inputs = {"prompts": ["m1", "m2", "m3"]}
        result = vectorized_op(inputs=batch_inputs)
        
        assert result["results"] == ["m1_module", "m2_module", "m3_module"]
        assert module_operator.processed_count == 3
    
    def test_vmap_with_complex_inputs(self):
        """Test vmap with complex nested input structures."""
        op = ComplexInputOperator()
        vectorized_op = vmap(op)
        
        # Complex batch inputs
        batch_inputs = {
            "prompts": ["c1", "c2"],
            "config": {"param": "value", "option": 123},
            "metadata": {"source": "test", "timestamp": 1000}
        }
        
        result = vectorized_op(inputs=batch_inputs)
        
        # Verify output structure and contents
        assert "results" in result
        assert len(result["results"]) == 2
        assert result["results"] == ["c1_complex", "c2_complex"]
        
        # Complex output fields should be properly handled
        assert "processed_config" in result
        assert len(result["processed_config"]) == 2
        
        assert "metadata" in result
        assert len(result["metadata"]) == 2
    
    def test_vmap_with_large_batch(self, basic_operator):
        """Test vmap with a large batch to ensure it scales properly."""
        vectorized_op = vmap(basic_operator)
        
        # Create a large batch
        batch_size = 1000
        batch_inputs = {
            "prompts": [f"large{i}" for i in range(batch_size)]
        }
        
        result = vectorized_op(inputs=batch_inputs)
        
        assert len(result["results"]) == batch_size
        assert basic_operator.call_count == batch_size
        
        # Verify a sample of results
        assert result["results"][0] == "large0_processed"
        assert result["results"][499] == "large499_processed"
        assert result["results"][-1] == f"large{batch_size-1}_processed"
    
    def test_vmap_preserves_order(self, basic_operator):
        """Test that vmap preserves the original order of inputs."""
        vectorized_op = vmap(basic_operator)
        
        # Use distinct prompts that can be easily checked for order
        batch_inputs = {
            "prompts": ["first", "second", "third", "fourth", "fifth"]
        }
        
        result = vectorized_op(inputs=batch_inputs)
        expected = ["first_processed", "second_processed", "third_processed", 
                    "fourth_processed", "fifth_processed"]
        assert result["results"] == expected


# =============================== Property-Based Tests ===============================

class TestVMapProperties:
    """Property-based tests for the vmap transformation."""
    
    def test_empty_input_property(self, basic_operator):
        """Property: vmap with empty inputs returns empty results."""
        vectorized_op = vmap(basic_operator)
        
        empty_inputs = [
            {},
            {"prompts": []},
            {"prompts": [], "config": {}},
            {"config": {}, "metadata": None}
        ]
        
        for inputs in empty_inputs:
            result = vectorized_op(inputs=inputs)
            assert "results" in result
            assert len(result["results"]) == 0
            
    def test_identity_property(self):
        """Property: vmap of identity function preserves inputs."""
        def identity_fn(*, inputs):
            """Identity function that returns inputs unchanged."""
            return {"results": inputs.get("prompts", [])}
        
        vectorized_identity = vmap(identity_fn)
        
        test_cases = [
            {"prompts": ["a", "b", "c"]},
            {"prompts": ["abc", "def", "ghi"]}
        ]
        
        for inputs in test_cases:
            result = vectorized_identity(inputs=inputs)
            assert result["results"] == inputs["prompts"]
    
    def test_composition_property(self):
        """Property: vmap commutes with function composition."""
        def f(*, inputs):
            """First transformation: append '_f'."""
            prompts = inputs.get("prompts", [])
            if isinstance(prompts, list):
                return {"results": [f"{p}_f" for p in prompts]}
            return {"results": [f"{prompts}_f"]}
            
        def g(*, inputs):
            """Second transformation: append '_g'."""
            prompts = inputs.get("prompts", [])
            if isinstance(prompts, list):
                return {"results": [f"{p}_g" for p in prompts]}
            return {"results": [f"{prompts}_g"]}
        
        # Approach 1: vmap(compose(f, g))
        def compose_fg(*, inputs):
            """Composition of f and g."""
            f_result = f(inputs=inputs)
            g_inputs = {"prompts": f_result["results"]}
            return g(inputs=g_inputs)
        
        vmap_compose = vmap(compose_fg)
        
        # Approach 2: compose(vmap(f), vmap(g))
        vmap_f = vmap(f)
        vmap_g = vmap(g)
        
        def compose_vmap_fg(*, inputs):
            """Composition of vmap(f) and vmap(g)."""
            f_result = vmap_f(inputs=inputs)
            g_inputs = {"prompts": f_result["results"]}
            return vmap_g(inputs=g_inputs)
        
        # Test both approaches produce the same results
        test_inputs = {"prompts": ["a", "b", "c"]}
        result1 = vmap_compose(inputs=test_inputs)
        result2 = compose_vmap_fg(inputs=test_inputs)
        
        assert result1["results"] == result2["results"]
    

# =============================== Edge Case Tests ===============================

class TestVMapEdgeCases:
    """Tests for vmap behavior in edge cases and corner cases."""
    
    def test_vmap_with_non_list_nested_inputs(self, basic_operator):
        """Test vmap with inputs that are not lists but contain nested data."""
        vectorized_op = vmap(basic_operator)
        
        # Nested dictionary
        nested_input = {
            "prompts": {"key1": "value1", "key2": "value2"}
        }
        
        # This should treat the dictionary as a single element
        result = vectorized_op(inputs=nested_input)
        assert len(result["results"]) == 1
        
        # Nested with mixed types
        mixed_input = {
            "prompts": [{"type": "dict"}, 123, "string"]
        }
        
        result = vectorized_op(inputs=mixed_input)
        assert len(result["results"]) == 3
    
    def test_vmap_with_nested_lists(self, basic_operator):
        """Test vmap with nested list structures."""
        vectorized_op = vmap(basic_operator)
        
        # Lists of lists
        nested_lists = {
            "prompts": [["a", "b"], ["c", "d"], ["e", "f"]]
        }
        
        result = vectorized_op(inputs=nested_lists)
        assert len(result["results"]) == 3
        
        # Each item should be a processed list
        # Note: The basic_operator processes inputs as-is, so each nested list is processed as a whole unit
        # rather than processing each element individually
        expected_results = []
        for nested_list in nested_lists["prompts"]:
            expected_results.append([f"{item}_processed" for item in nested_list])
            
        # Convert to strings for comparison 
        expected_str = [str(x) for x in expected_results]
        result_str = [str(x) for x in result["results"]]
        
        assert result_str == expected_str
    
    def test_vmap_with_special_characters(self, basic_operator):
        """Test vmap with inputs containing special characters."""
        vectorized_op = vmap(basic_operator)
        
        special_chars = {
            "prompts": ["line\nbreak", "tab\tchar", "quote\"quote", "emoji🔥"]
        }
        
        result = vectorized_op(inputs=special_chars)
        assert len(result["results"]) == 4
        
        # Each special character string should be processed correctly
        for i, prompt in enumerate(special_chars["prompts"]):
            assert result["results"][i] == f"{prompt}_processed"
    
    def test_vmap_with_none_values(self, basic_operator):
        """Test vmap with None values in inputs."""
        vectorized_op = vmap(basic_operator)
        
        none_inputs = {
            "prompts": [None, "valid", None]
        }
        
        result = vectorized_op(inputs=none_inputs)
        assert len(result["results"]) == 3
        assert result["results"][0] == "None_processed"
        assert result["results"][1] == "valid_processed"
        assert result["results"][2] == "None_processed"
        
    def test_vmap_with_multiple_batched_fields(self):
        """Test vmap with multiple fields that can be batched."""
        def multi_field_fn(*, inputs):
            """Process inputs with multiple fields."""
            prompts = inputs.get("prompts", [])
            contexts = inputs.get("contexts", [])
            
            results = []
            if isinstance(prompts, list) and isinstance(contexts, list):
                # If we have both, combine them
                for p, c in zip(prompts, contexts):
                    results.append(f"{p}+{c}")
            elif isinstance(prompts, list):
                results = [f"{p}+default" for p in prompts]
            elif isinstance(contexts, list):
                results = [f"default+{c}" for c in contexts]
            else:
                results = [f"{prompts}+{contexts}"]
                
            return {"results": results}
        
        vectorized_fn = vmap(multi_field_fn)
        
        # Test with multiple batched fields of same length
        multi_inputs = {
            "prompts": ["p1", "p2", "p3"],
            "contexts": ["c1", "c2", "c3"]
        }
        
        result = vectorized_fn(inputs=multi_inputs)
        assert result["results"] == ["p1+c1", "p2+c2", "p3+c3"]
        
        # Test with inconsistent lengths (should raise error)
        inconsistent_inputs = {
            "prompts": ["p1", "p2"],
            "contexts": ["c1", "c2", "c3"]
        }
        
        with pytest.raises(ValueError, match="Inconsistent batch sizes"):
            vectorized_fn(inputs=inconsistent_inputs)


# =============================== Performance Tests ===============================

class TestVMapPerformance:
    """Tests focused on the performance characteristics of vmap."""
    
    def test_vmap_performance_with_varying_batch_size(self, basic_operator):
        """Test how vmap performance scales with batch size."""
        # Skip this test by default as it's a performance test
        try:
            if not pytest.config.getoption("--run-perf-tests", default=False):
                pytest.skip("Performance tests are disabled by default")
        except (AttributeError, TypeError):
            # Handle pytest.config not being available or other errors
            pytest.skip("Performance tests are disabled by default")
            
        vectorized_op = vmap(basic_operator)
        
        batch_sizes = [10, 100, 1000]
        times = []
        
        for size in batch_sizes:
            batch_inputs = generate_batch_inputs(size)
            
            start_time = time.time()
            result = vectorized_op(inputs=batch_inputs)
            end_time = time.time()
            
            assert len(result["results"]) == size
            times.append(end_time - start_time)
            
        # Verify that time scales roughly linearly with batch size
        # (with some allowance for overhead and optimization)
        assert times[1] < times[0] * 15  # 100 items should be less than 15x the time of 10 items
        assert times[2] < times[1] * 15  # 1000 items should be less than 15x the time of 100 items


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])