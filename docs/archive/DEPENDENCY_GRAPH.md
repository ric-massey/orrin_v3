# Dependency Graph — Orrin v3

> **Note (2026-06-01):** Auto-generated. Module names were updated for the bio→computational
> rename (e.g. `affect.amygdala`→`affect.threat_detector`), but the graph predates later
> file moves — **regenerate** it to get an accurate current dependency map.

Generated from 329 .py files.

---

## `brain/ORRIN_loop.py`
**Imports:**
  - `brain/affect/affect.py`
  - `brain/affect/affect_drift.py`
  - `brain/affect/affect_learning.py`
  - `brain/affect/apply_affective_feedback.py`
  - `brain/affect/stagnation_signal_escalation.py`
  - `brain/affect/consolidation.py`
  - `brain/affect/integration_lag.py`
  - `brain/affect/modes_and_affect.py`
  - `brain/affect/reflect_on_affect.py`
  - `brain/affect/reflect_on_affect_model.py`
  - `brain/affect/regulation.py`
  - `brain/affect/update_affect_state.py`
  - `brain/agency/code_writer.py`
  - `brain/agency/skills/grep_files.py`
  - `brain/agency/skills/list_directory.py`
  - `brain/agency/skills/notify_user.py`
  - `brain/agency/skills/save_note.py`
  - `brain/agency/skills/search_files.py`
  - `brain/agency/tool_runner.py`
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/awaiting_response.py`
  - `brain/cognition/behavioral_adaptation.py`
  - `brain/cognition/body_sense.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/experimentation.py`
  - `brain/cognition/finetuning/finetune_pipeline.py`
  - `brain/cognition/health_monitor.py`
  - `brain/cognition/innovation/evaluation.py`
  - `brain/cognition/intrinsic_goals.py`
  - `brain/cognition/leave_note.py`
  - `brain/cognition/local_search_signal.py`
  - `brain/cognition/metacog.py`
  - `brain/cognition/perception/fs_perception.py`
  - `brain/cognition/perception/look_around.py`
  - `brain/cognition/perception/look_outward.py`
  - `brain/cognition/planning/env_snapshot.py`
  - `brain/cognition/planning/goal_lifecycle.py`
  - `brain/cognition/planning/goal_progress.py`
  - `brain/cognition/planning/pursue_goal.py`
  - `brain/cognition/planning/reflection.py`
  - `brain/cognition/planning/thinking_depth.py`
  - `brain/cognition/prediction.py`
  - `brain/cognition/privacy.py`
  - `brain/cognition/reflection_metadata.py`
  - `brain/cognition/repair/auto_repair.py`
  - `brain/cognition/repair/repair.py`
  - `brain/cognition/search_own_files.py`
  - `brain/cognition/self_extension.py`
  - `brain/cognition/selfhood/autobiography.py`
  - `brain/cognition/selfhood/latent_identity.py`
  - `brain/cognition/selfhood/person_detector.py`
  - `brain/cognition/selfhood/tensions.py`
  - `brain/cognition/selfhood/value_evolution.py`
  - `brain/cognition/terminal.py`
  - `brain/cognition/threads.py`
  - `brain/cognition/wonder.py`
  - `brain/core/manager.py`
  - `brain/embodiment/setpoint_regulation.py`
  - `brain/embodiment/system_presence.py`
  - `brain/eval/evaluator_daemon.py`
  - `brain/eval/evaluator_wal.py`
  - `brain/goals_bridge.py`
  - `brain/memory_bridge.py`
  - `brain/paths.py`
  - `brain/peers/peer_registry.py`
  - `brain/registry/behavior_registry.py`
  - `brain/registry/cognition_registry.py`
  - `brain/symbolic/autonomous_experiment.py`
  - `brain/symbolic/benchmark.py`
  - `brain/symbolic/embodied_actions.py`
  - `brain/symbolic/ground_truth.py`
  - `brain/symbolic/intrinsic_motivation.py`
  - `brain/symbolic/prediction_engine.py`
  - `brain/symbolic/reasoning_router.py`
  - `brain/symbolic/rule_compressor.py`
  - `brain/symbolic/rule_forgetting.py`
  - `brain/symbolic/self_improvement.py`
  - `brain/symbolic/symbolic_dream.py`
  - `brain/think/loop_helpers.py`
  - `brain/think/meta_controller.py`
  - `brain/think/thalamus.py`
  - `brain/think/think_generate.py`
  - `brain/think/think_module.py`
  - `brain/think/think_utils/action_gate.py`
  - `brain/think/think_utils/select_function.py`
  - `brain/utils/emotion_utils.py`
  - `brain/utils/error_router.py`
  - `brain/utils/failure_counter.py`
  - `brain/utils/get_cycle_count.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/load_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/runtime_ctx.py`
  - `brain/utils/self_model.py`
  - `brain/utils/signal_utils.py`
  - `brain/utils/state_guard.py`
  - `brain/utils/token_meter.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/affect/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/affect/affect.py`
**Imports:**
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/coerce_to_string.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (11 files)
  - `brain/ORRIN_loop.py`
  - `brain/affect/affect_drift.py`
  - `brain/affect/reflect_on_affect.py`
  - `brain/affect/update_affect_state.py`
  - `brain/cog_memory/chat_log.py`
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/remember.py`
  - `brain/cog_memory/summarize_w_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/comprehension.py`
  - `brain/cognition/contagion.py`

## `brain/affect/affect_buffer.py`
**Imports:**
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/affect/update_affect_state.py`

## `brain/affect/affect_drift.py`
**Imports:**
  - `brain/affect/affect.py`
  - `brain/affect/modes_and_affect.py`
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/ORRIN_loop.py`
  - `brain/affect/apply_affective_feedback.py`
  - `brain/think/think_utils/dreams_emotional_logic.py`

## `brain/affect/affect_dynamics.py`
**Imports:** *(none within project)*
**Imported by:** (2 files)
  - `brain/affect/affect_summary.py`
  - `brain/affect/update_affect_state.py`

## `brain/affect/affect_learning.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
**Imported by:** (4 files)
  - `brain/ORRIN_loop.py`
  - `brain/embodiment/plasticity.py`
  - `brain/think/think_module.py`
  - `brain/think/think_utils/action_gate.py`

## `brain/affect/affect_summary.py`
**Imports:**
  - `brain/affect/affect_dynamics.py`
**Imported by:** (4 files)
  - `brain/behavior/speech_gate.py`
  - `brain/cognition/selfhood/identity.py`
  - `brain/think/inner_loop.py`
  - `brain/think/state_processor.py`

## `brain/affect/threat_detector.py`
**Imports:**
  - `brain/utils/emotion_utils.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/core/drive.py`
  - `brain/think/think_utils/dreams_emotional_logic.py`
  - `brain/utils/emotional_response.py`

## `brain/affect/apply_affective_feedback.py`
**Imports:**
  - `brain/affect/affect_drift.py`
  - `brain/affect/modes_and_affect.py`
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/affect/update_affect_state.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/utils/emotion_utils.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/think/think_utils/dreams_emotional_logic.py`

## `brain/affect/appraisal.py`
**Imports:** *(none within project)*
**Imported by:** (1 files)
  - `brain/affect/update_affect_state.py`

## `brain/affect/stagnation_signal_escalation.py`
**Imports:**
  - `brain/utils/log.py`
  - `brain/utils/signal_utils.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/affect/consolidation.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/cog_memory/working_memory.py`

## `brain/affect/discovery.py`
**Imports:**
  - `brain/affect/reflect_on_affect_model.py`
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/self_model.py`
**Imported by:** (1 files)
  - `brain/affect/reflect_on_affect.py`

## `brain/affect/integration_lag.py`
**Imports:**
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/comprehension.py`

## `brain/affect/introspection.py`
**Imports:** *(none within project)*
**Imported by:** (2 files)
  - `brain/cognition/selfhood/identity.py`
  - `brain/think/think_module.py`

## `brain/affect/model.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/utils/emotion_utils.py`

## `brain/affect/modes_and_affect.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (5 files)
  - `brain/ORRIN_loop.py`
  - `brain/affect/affect_drift.py`
  - `brain/affect/apply_affective_feedback.py`
  - `brain/affect/update_affect_state.py`
  - `brain/think/think_utils/select_function.py`

## `brain/affect/reflect_on_affect.py`
**Imports:**
  - `brain/affect/affect.py`
  - `brain/affect/discovery.py`
  - `brain/affect/reflect_on_affect_model.py`
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/symbolic/crystallization.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/symbolic/symbolic_reflection.py`
  - `brain/utils/coerce_to_string.py`
  - `brain/utils/load_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/log_reflection.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/think/think_utils/dreams_emotional_logic.py`

## `brain/affect/reflect_on_affect_model.py`
**Imports:**
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/symbolic/crystallization.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/symbolic/symbolic_reflection.py`
  - `brain/utils/load_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/log_reflection.py`
**Imported by:** (3 files)
  - `brain/ORRIN_loop.py`
  - `brain/affect/discovery.py`
  - `brain/affect/reflect_on_affect.py`

## `brain/affect/regulation.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/think/think_utils/finalize.py`

## `brain/affect/reward_signals/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/affect/reward_signals/action_reward_ema.py`
**Imports:**
  - `brain/utils/json_utils.py`
**Imported by:** (5 files)
  - `brain/cognition/planning/goal_lifecycle.py`
  - `brain/cognition/planning/goals.py`
  - `brain/cognition/planning/pursue_goal.py`
  - `brain/think/think_utils/action_gate.py`
  - `brain/think/think_utils/execute_cognitive_actions.py`

## `brain/affect/reward_signals/resource_deficit.py`
**Imports:** *(none within project)*
**Imported by:** (2 files)
  - `brain/think/think_utils/action_gate.py`
  - `brain/think/think_utils/dreams_emotional_logic.py`

## `brain/affect/reward_signals/reward_signals.py`
**Imports:**
  - `brain/affect/affect_buffer.py`
  - `brain/affect/reward_signals/reward_spike.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/signal_utils.py`
**Imported by:** (25 files)
  - `brain/affect/affect.py`
  - `brain/affect/affect_drift.py`
  - `brain/affect/apply_affective_feedback.py`
  - `brain/affect/discovery.py`
  - `brain/affect/reflect_on_affect.py`
  - `brain/affect/reflect_on_affect_model.py`
  - `brain/cog_memory/long_memory.py`
  - `brain/cognition/planning/goal_lifecycle.py`
  - `brain/cognition/planning/goals.py`
  - `brain/cognition/planning/motivations.py`
  - `brain/cognition/planning/pursue_goal.py`
  - `brain/cognition/reflection/reflect_on_self_belief.py`
  - `brain/cognition/repair/repair.py`
  - `brain/cognition/reward_calibrator.py`
  - `brain/cognition/selfhood/fragmentation.py`
  - `brain/cognition/temporal_pressure.py`
  - `brain/think/thalamus.py`
  - `brain/think/think_utils/action_gate.py`
  - `brain/think/think_utils/dreams_emotional_logic.py`
  - `brain/think/think_utils/execute_cognitive_actions.py`
  - `brain/think/think_utils/finalize.py`
  - `brain/think/think_utils/reflect_on_directive.py`
  - `brain/think/think_utils/user_input.py`
  - `brain/utils/emotion_utils.py`
  - `brain/utils/feedback_log.py`

## `brain/affect/reward_signals/reward_spike.py`
**Imports:**
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/affect/reward_signals/reward_signals.py`

## `brain/affect/update_affect_state.py`
**Imports:**
  - `brain/affect/affect.py`
  - `brain/affect/affect_buffer.py`
  - `brain/affect/affect_dynamics.py`
  - `brain/affect/appraisal.py`
  - `brain/affect/modes_and_affect.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/body_sense.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/timing.py`
**Imported by:** (6 files)
  - `brain/ORRIN_loop.py`
  - `brain/affect/apply_affective_feedback.py`
  - `brain/cognition/reflection/reflect_on_self_belief.py`
  - `brain/think/loop_helpers.py`
  - `brain/think/think_utils/dreams_emotional_logic.py`
  - `brain/think/think_utils/finalize.py`

## `brain/agency/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/agency/code_writer.py`
**Imports:**
  - `brain/behavior/tools/toolkit.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/skill_synthesis.py`
  - `brain/paths.py`
  - `brain/registry/cognition_registry.py`
  - `brain/think/sandbox_runner.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/agency/skills/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/agency/skills/grep_files.py`
**Imports:**
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/search_own_files.py`

## `brain/agency/skills/list_directory.py`
**Imports:**
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/agency/skills/notify_user.py`
**Imports:**
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/agency/skills/save_note.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/agency/skills/search_files.py`
**Imports:**
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/agency/tool_runner.py`
**Imports:**
  - `brain/behavior/tools/toolkit.py`
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/failure_counter.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/ORRIN_loop.py`
  - `brain/behavior/tools/tool_executor.py`
  - `brain/cognition/perception/look_outward.py`

## `brain/alive_brain.py`
**Imports:**
  - `brain/events.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/behavior/behavior_generation.py`
**Imports:**
  - `brain/cognition/behavior.py`
  - `brain/paths.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/goals.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/think/think_utils/action_gate.py`
  - `brain/think/think_utils/dreams_emotional_logic.py`

## `brain/behavior/dynamic_loader.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/log.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/behavior/expression.py`
**Imports:**
  - `brain/think/cycle_state.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/think/think_utils/action_gate.py`

## `brain/behavior/pre_speak_check.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/think/think_utils/action_gate.py`

## `brain/behavior/revise.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/reflection/meta_reflect.py`
  - `brain/paths.py`
  - `brain/think/sandbox_runner.py`
  - `brain/utils/append.py`
  - `brain/utils/code_validation.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
  - `brain/utils/self_model.py`
  - `brain/utils/summarizers.py`
**Imported by:** (1 files)
  - `brain/cognition/repair/auto_repair.py`

## `brain/behavior/speak.py`
**Imports:**
  - `brain/cog_memory/chat_log.py`
  - `brain/cognition/body_sense.py`
  - `brain/cognition/opinions.py`
  - `brain/cognition/privacy.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (4 files)
  - `brain/cognition/terminal.py`
  - `brain/think/think_module.py`
  - `brain/think/think_utils/action_gate.py`
  - `brain/think/think_utils/talk_policy.py`

## `brain/behavior/speech_gate.py`
**Imports:**
  - `brain/affect/affect_summary.py`
  - `brain/think/speech_generator.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/think/think_utils/talk_policy.py`

## `brain/behavior/speech_pipeline.py`
**Imports:**
  - `brain/cognition/opinions.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/log.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/behavior/tools/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/behavior/tools/sandbox.py`
**Imports:**
  - `brain/paths.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/behavior/tools/tool_executor.py`
**Imports:**
  - `brain/agency/tool_runner.py`
  - `brain/behavior/tools/toolkit.py`
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/events.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/behavior/tools/toolkit.py`
**Imports:**
  - `brain/paths.py`
  - `brain/think/sandbox_runner.py`
  - `brain/utils/core_utils.py`
  - `brain/utils/error_router.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (4 files)
  - `brain/agency/code_writer.py`
  - `brain/agency/tool_runner.py`
  - `brain/behavior/tools/tool_executor.py`
  - `brain/think/think_utils/finalize.py`

## `brain/cog_memory/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/cog_memory/chat_log.py`
**Imports:**
  - `brain/affect/affect.py`
  - `brain/cog_memory/long_memory.py`
  - `brain/paths.py`
  - `brain/utils/append.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/behavior/speak.py`
  - `brain/think/think_utils/user_input.py`

## `brain/cog_memory/long_memory.py`
**Imports:**
  - `brain/affect/affect.py`
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/cognition/selfhood/ethics.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/memory_graph.py`
  - `brain/utils/memory_utils.py`
**Imported by:** (44 files)
  - `brain/ORRIN_loop.py`
  - `brain/agency/tool_runner.py`
  - `brain/behavior/tools/tool_executor.py`
  - `brain/cog_memory/chat_log.py`
  - `brain/cog_memory/remember.py`
  - `brain/cog_memory/summarize_w_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/awaiting_response.py`
  - `brain/cognition/body_sense.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/experimentation.py`
  - `brain/cognition/innovation/bootstrap.py`
  - `brain/cognition/innovation/evaluation.py`
  - `brain/cognition/intrinsic_goals.py`
  - `brain/cognition/opinions.py`
  - `brain/cognition/perception/look_around.py`
  - `brain/cognition/perception/look_outward.py`
  - `brain/cognition/planning/evolution.py`
  - `brain/cognition/planning/goals.py`
  - `brain/cognition/planning/pursue_goal.py`
  - `brain/cognition/planning/reflection.py`
  - `brain/cognition/prediction.py`
  - `brain/cognition/reflection/reflect_on_outcome.py`
  - `brain/cognition/reflection_metadata.py`
  - `brain/cognition/regret.py`
  - `brain/cognition/rss_reader.py`
  - `brain/cognition/search_own_files.py`
  - `brain/cognition/seek_novelty.py`
  - `brain/cognition/self_extension.py`
  - `brain/cognition/selfhood/autobiography.py`
  - `brain/cognition/selfhood/fragmentation.py`
  - `brain/cognition/selfhood/value_evolution.py`
  - `brain/cognition/selfhood/values_check.py`
  - `brain/cognition/threads.py`
  - `brain/cognition/tools/ask_llm.py`
  - `brain/cognition/web_research.py`
  - `brain/cognition/wikipedia_search.py`
  - `brain/cognition/wonder.py`
  - `brain/embodiment/system_presence.py`
  - `brain/embodiment/world_model.py`
  - `brain/goals_bridge.py`
  - `brain/motivation/substrate.py`
  - `brain/think/thalamus.py`
  - `brain/think/think_utils/execute_cognitive_actions.py`

## `brain/cog_memory/reconstruction.py`
**Imports:** *(none within project)*
**Imported by:** (3 files)
  - `brain/cognition/selfhood/autobiography.py`
  - `brain/memory_bridge.py`
  - `brain/think/state_processor.py`

## `brain/cog_memory/remember.py`
**Imports:**
  - `brain/affect/affect.py`
  - `brain/cog_memory/long_memory.py`
  - `brain/paths.py`
  - `brain/utils/embedder.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/cognition/reflection/reflect_on_self_belief.py`
  - `brain/cognition/repair/repair.py`
  - `brain/cognition/sandbox.py`

## `brain/cog_memory/summarize_w_memory.py`
**Imports:**
  - `brain/affect/affect.py`
  - `brain/cog_memory/long_memory.py`
  - `brain/utils/embedder.py`
  - `brain/utils/log.py`
  - `brain/utils/memory_utils.py`
**Imported by:** (1 files)
  - `brain/cog_memory/working_memory.py`

## `brain/cog_memory/working_memory.py`
**Imports:**
  - `brain/affect/affect.py`
  - `brain/affect/consolidation.py`
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/summarize_w_memory.py`
  - `brain/paths.py`
  - `brain/utils/embedder.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (74 files)
  - `brain/ORRIN_loop.py`
  - `brain/affect/affect.py`
  - `brain/affect/affect_drift.py`
  - `brain/affect/apply_affective_feedback.py`
  - `brain/affect/discovery.py`
  - `brain/affect/modes_and_affect.py`
  - `brain/affect/reflect_on_affect.py`
  - `brain/affect/reflect_on_affect_model.py`
  - `brain/affect/regulation.py`
  - `brain/affect/update_affect_state.py`
  - `brain/agency/code_writer.py`
  - `brain/agency/tool_runner.py`
  - `brain/behavior/revise.py`
  - `brain/behavior/tools/tool_executor.py`
  - `brain/cognition/associative_memory.py`
  - `brain/cognition/awaiting_response.py`
  - `brain/cognition/cognitive_cost.py`
  - `brain/cognition/comprehension.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/experimentation.py`
  - `brain/cognition/goal_competition.py`
  - `brain/cognition/health_monitor.py`
  - `brain/cognition/innovation/bootstrap.py`
  - `brain/cognition/innovation/evaluation.py`
  - `brain/cognition/innovation/exploration.py`
  - `brain/cognition/innovation/innovation.py`
  - `brain/cognition/metacog.py`
  - `brain/cognition/mortality.py`
  - `brain/cognition/opinions.py`
  - `brain/cognition/perception/environment.py`
  - `brain/cognition/perception/look_around.py`
  - `brain/cognition/planning/evolution.py`
  - `brain/cognition/planning/goals.py`
  - `brain/cognition/planning/introspection.py`
  - `brain/cognition/planning/motivations.py`
  - `brain/cognition/planning/pursue_goal.py`
  - `brain/cognition/planning/reflection.py`
  - `brain/cognition/reflection/reflect_on_cognition.py`
  - `brain/cognition/reflection/reflect_on_cognition_schedule.py`
  - `brain/cognition/reflection/reflect_on_internal_agents.py`
  - `brain/cognition/reflection/reflect_on_outcome.py`
  - `brain/cognition/reflection/reflect_on_self_belief.py`
  - `brain/cognition/reflection/rule_reflection.py`
  - `brain/cognition/reflection/self_reflection.py`
  - `brain/cognition/reflection_metadata.py`
  - `brain/cognition/regret.py`
  - `brain/cognition/repair/auto_repair.py`
  - `brain/cognition/repair/repair.py`
  - `brain/cognition/rumination.py`
  - `brain/cognition/sandbox.py`
  - `brain/cognition/search_own_files.py`
  - `brain/cognition/self_extension.py`
  - `brain/cognition/self_generated/autogenerated_thoughts.py`
  - `brain/cognition/selfhood/fragmentation.py`
  - `brain/cognition/selfhood/relationships.py`
  - `brain/cognition/selfhood/self_model_conflicts.py`
  - `brain/cognition/selfhood/tensions.py`
  - `brain/cognition/temporal_pressure.py`
  - `brain/cognition/tools/ask_llm.py`
  - `brain/cognition/web_research.py`
  - `brain/cognition/world_model.py`
  - `brain/core/drive.py`
  - `brain/embodiment/subconscious.py`
  - `brain/symbolic/embodied_actions.py`
  - `brain/symbolic/symbolic_dream.py`
  - `brain/think/scratchpad.py`
  - `brain/think/think_module.py`
  - `brain/think/think_utils/action_gate.py`
  - `brain/think/think_utils/dreams_emotional_logic.py`
  - `brain/think/think_utils/execute_cognitive_actions.py`
  - `brain/think/think_utils/finalize.py`
  - `brain/think/think_utils/reflect_on_directive.py`
  - `brain/think/think_utils/user_input.py`
  - `brain/utils/emotional_feedback.py`

## `brain/cognition/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/ambient_thought.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/think/think_module.py`

## `brain/cognition/associative_memory.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/knowledge_graph.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/think/think_utils/finalize.py`

## `brain/cognition/attention.py`
**Imports:** *(none within project)*
**Imported by:** (1 files)
  - `brain/think/thalamus.py`

## `brain/cognition/awaiting_response.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/threads.py`
  - `brain/utils/log.py`
  - `brain/utils/signal_utils.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/cognition/behavior.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/behavior/behavior_generation.py`
  - `brain/think/think_utils/action_gate.py`

## `brain/cognition/behavioral_adaptation.py`
**Imports:**
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/metacog.py`

## `brain/cognition/body_sense.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/ORRIN_loop.py`
  - `brain/affect/update_affect_state.py`
  - `brain/behavior/speak.py`

## `brain/cognition/cognitive_cost.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/cognition/regret.py`
  - `brain/think/think_utils/action_gate.py`
  - `brain/think/think_utils/finalize.py`

## `brain/cognition/comprehension.py`
**Imports:**
  - `brain/affect/affect.py`
  - `brain/affect/integration_lag.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/contagion.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/think/think_utils/user_input.py`

## `brain/cognition/concept_memory.py`
**Imports:**
  - `brain/utils/json_utils.py`
**Imported by:** (1 files)
  - `brain/think/think_module.py`

## `brain/cognition/contagion.py`
**Imports:**
  - `brain/affect/affect.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/cognition/comprehension.py`
  - `brain/think/think_utils/user_input.py`

## `brain/cognition/custom_cognition/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/dreaming/__init__.py`
**Imports:**
  - `brain/cognition/dreaming/compose.py`
  - `brain/cognition/dreaming/dream_cycle.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/dreaming/compose.py`
**Imports:** *(none within project)*
**Imported by:** (1 files)
  - `brain/cognition/dreaming/__init__.py`

## `brain/cognition/dreaming/dream_cycle.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/dreaming/episode_replay.py`
  - `brain/cognition/dreaming/semantic_extractor.py`
  - `brain/cognition/experimentation.py`
  - `brain/cognition/intrinsic_goals.py`
  - `brain/cognition/knowledge_graph.py`
  - `brain/cognition/planning/evolution.py`
  - `brain/cognition/prediction.py`
  - `brain/cognition/reflection_metadata.py`
  - `brain/cognition/selfhood/autobiography.py`
  - `brain/cognition/selfhood/latent_identity.py`
  - `brain/cognition/selfhood/tensions.py`
  - `brain/cognition/skill_synthesis.py`
  - `brain/cognition/wonder.py`
  - `brain/cognition/world_model.py`
  - `brain/paths.py`
  - `brain/symbolic/autonomous_experiment.py`
  - `brain/symbolic/benchmark.py`
  - `brain/symbolic/causal_graph.py`
  - `brain/symbolic/concept_formation.py`
  - `brain/symbolic/crystallization.py`
  - `brain/symbolic/embodied_actions.py`
  - `brain/symbolic/ground_truth.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/symbolic/prediction_engine.py`
  - `brain/symbolic/progress_tracker.py`
  - `brain/symbolic/rule_abstraction.py`
  - `brain/symbolic/rule_compressor.py`
  - `brain/symbolic/rule_forgetting.py`
  - `brain/symbolic/rule_synthesis.py`
  - `brain/symbolic/rule_verifier.py`
  - `brain/symbolic/self_improvement.py`
  - `brain/symbolic/symbolic_cognition.py`
  - `brain/symbolic/symbolic_dream.py`
  - `brain/symbolic/symbolic_self_model.py`
  - `brain/symbolic/temporal_planner.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
  - `brain/utils/self_model.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/dreaming/__init__.py`

## `brain/cognition/dreaming/episode_replay.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/cognition/dreaming/dream_cycle.py`

## `brain/cognition/dreaming/semantic_extractor.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/cognition/dreaming/dream_cycle.py`

## `brain/cognition/dreaming.py`
**Imports:** *(none within project)*
**Imported by:** (1 files)
  - `brain/think/think_utils/dreams_emotional_logic.py`

## `brain/cognition/emotion_routing.py`
**Imports:** *(none within project)*
**Imported by:** (1 files)
  - `brain/think/think_utils/select_function.py`

## `brain/cognition/experimentation.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/knowledge_graph.py`
  - `brain/paths.py`
  - `brain/think/think_utils/select_function.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/dreaming/dream_cycle.py`

## `brain/cognition/finetuning/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/finetuning/finetune_pipeline.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/trace_buffer.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/cognition/goal_competition.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/think/think_utils/select_function.py`

## `brain/cognition/habituation.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/think/think_utils/finalize.py`

## `brain/cognition/health_monitor.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/embodiment/setpoint_regulation.py`
  - `brain/think/bandit/contextual_bandit.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/cognition/inhibition.py`
**Imports:**
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/think/think_utils/select_function.py`

## `brain/cognition/innovation/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/innovation/bootstrap.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
  - `brain/utils/self_model.py`
  - `brain/utils/signal_utils.py`
  - `brain/utils/summarizers.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/innovation/evaluation.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/think/bandit/contextual_bandit.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
  - `brain/utils/self_model.py`
  - `brain/utils/signal_utils.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/cognition/innovation/exploration.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/append.py`
  - `brain/utils/core_utils.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/innovation/innovation.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/append.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
  - `brain/utils/self_model.py`
  - `brain/utils/summarizers.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/intrinsic_goals.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/cognition/planning/goal_lifecycle.py`
  - `brain/cognition/planning/goals.py`
  - `brain/paths.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
**Imported by:** (4 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/planning/goals.py`
  - `brain/cognition/planning/pursue_goal.py`

## `brain/cognition/knowledge_formation.py`
**Imports:**
  - `brain/symbolic/causal_graph.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/cognition/metacog.py`

## `brain/cognition/knowledge_graph.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
**Imported by:** (10 files)
  - `brain/cognition/associative_memory.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/experimentation.py`
  - `brain/cognition/perception/environment.py`
  - `brain/cognition/perception/look_outward.py`
  - `brain/cognition/skill_synthesis.py`
  - `brain/symbolic/concept_formation.py`
  - `brain/symbolic/rule_forgetting.py`
  - `brain/symbolic/symbolic_search.py`
  - `brain/think/think_module.py`

## `brain/cognition/leave_note.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/planning/pursue_goal.py`

## `brain/cognition/local_search_signal.py`
**Imports:**
  - `brain/utils/log.py`
  - `brain/utils/signal_utils.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/cognition/maintenance/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/maintenance/self_modeling.py`
**Imports:**
  - `brain/paths.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/symbolic/symbolic_cognition.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/self_model.py`
**Imported by:** (2 files)
  - `brain/cognition/reflection/meta_reflect.py`
  - `brain/cognition/reflection/reflect_on_self_belief.py`

## `brain/cognition/maintenance/self_review.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/append.py`
  - `brain/utils/events_miner.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/log_reflection.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/metacog.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/behavioral_adaptation.py`
  - `brain/cognition/knowledge_formation.py`
  - `brain/paths.py`
  - `brain/think/bandit/contextual_bandit.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/ORRIN_loop.py`
  - `brain/think/scratchpad.py`
  - `brain/think/think_module.py`

## `brain/cognition/mood.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/think/think_utils/finalize.py`

## `brain/cognition/mortality.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/think/think_utils/finalize.py`

## `brain/cognition/opinions.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/behavior/speak.py`
  - `brain/behavior/speech_pipeline.py`
  - `brain/think/think_utils/finalize.py`

## `brain/cognition/perception/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/perception/environment.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/knowledge_graph.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/cognition/perception/look_around.py`
  - `brain/think/think_utils/finalize.py`

## `brain/cognition/perception/file_sense.py`
**Imports:** *(none within project)*
**Imported by:** (4 files)
  - `brain/cognition/perception/fs_perception.py`
  - `brain/cognition/search_own_files.py`
  - `brain/peers/architect.py`
  - `brain/peers/observer.py`

## `brain/cognition/perception/fs_perception.py`
**Imports:**
  - `brain/cognition/perception/file_sense.py`
  - `brain/utils/log.py`
  - `brain/utils/signal_utils.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/cognition/perception/look_around.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/perception/environment.py`
  - `brain/embodiment/world_model.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/cognition/perception/look_outward.py`
**Imports:**
  - `brain/agency/tool_runner.py`
  - `brain/cog_memory/long_memory.py`
  - `brain/cognition/knowledge_graph.py`
  - `brain/cognition/search_own_files.py`
  - `brain/paths.py`
  - `brain/utils/failure_counter.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/seek_novelty.py`

## `brain/cognition/planning/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/planning/env_snapshot.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/failure_counter.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/cognition/planning/evolution.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/failure_counter.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
  - `brain/utils/self_model.py`
  - `brain/utils/summarizers.py`
**Imported by:** (1 files)
  - `brain/cognition/dreaming/dream_cycle.py`

## `brain/cognition/planning/goal_lifecycle.py`
**Imports:**
  - `brain/affect/reward_signals/action_reward_ema.py`
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/intrinsic_goals.py`
  - `brain/cognition/planning/goals.py`

## `brain/cognition/planning/goal_progress.py`
**Imports:** *(none within project)*
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/cognition/planning/goals.py`
**Imports:**
  - `brain/affect/reward_signals/action_reward_ema.py`
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/intrinsic_goals.py`
  - `brain/cognition/planning/goal_lifecycle.py`
  - `brain/cognition/threads.py`
  - `brain/paths.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/signal_utils.py`
**Imported by:** (5 files)
  - `brain/cognition/intrinsic_goals.py`
  - `brain/cognition/planning/pursue_goal.py`
  - `brain/cognition/reflection/reflect_on_self_belief.py`
  - `brain/goals_bridge.py`
  - `brain/think/think_utils/action_gate.py`

## `brain/cognition/planning/goals_schema.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/planning/introspection.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/planning/motivations.py`
  - `brain/cognition/planning/reflection.py`
  - `brain/paths.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
  - `brain/utils/log_reflection.py`
  - `brain/utils/self_model.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/planning/motivations.py`
**Imports:**
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
  - `brain/utils/self_model.py`
**Imported by:** (2 files)
  - `brain/cognition/planning/introspection.py`
  - `brain/think/think_utils/finalize.py`

## `brain/cognition/planning/pursue_goal.py`
**Imports:**
  - `brain/affect/reward_signals/action_reward_ema.py`
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/intrinsic_goals.py`
  - `brain/cognition/leave_note.py`
  - `brain/cognition/planning/goals.py`
  - `brain/cognition/planning/thinking_depth.py`
  - `brain/cognition/search_own_files.py`
  - `brain/cognition/web_research.py`
  - `brain/cognition/wikipedia_search.py`
  - `brain/paths.py`
  - `brain/think/inner_loop.py`
  - `brain/think/scratchpad.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/cognition/planning/reflection.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/load_utils.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/planning/introspection.py`
  - `brain/cognition/reflection/meta_reflect.py`

## `brain/cognition/planning/thinking_depth.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/planning/pursue_goal.py`
  - `brain/think/meta_controller.py`

## `brain/cognition/prediction.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/paths.py`
  - `brain/symbolic/causal_graph.py`
  - `brain/symbolic/prediction_engine.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/signal_utils.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/dreaming/dream_cycle.py`

## `brain/cognition/privacy.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/behavior/speak.py`

## `brain/cognition/reflection/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/reflection/meta_reflect.py`
**Imports:**
  - `brain/cognition/maintenance/self_modeling.py`
  - `brain/cognition/planning/reflection.py`
  - `brain/cognition/reflection/reflect_on_cognition.py`
  - `brain/cognition/reflection/reflect_on_outcome.py`
  - `brain/cognition/reflection/reflect_on_self_belief.py`
  - `brain/cognition/reflection/rule_reflection.py`
  - `brain/cognition/reflection/self_reflection.py`
  - `brain/cognition/repair/repair.py`
  - `brain/cognition/selfhood/self_model_conflicts.py`
  - `brain/cognition/world_model.py`
  - `brain/paths.py`
  - `brain/symbolic/self_improvement.py`
  - `brain/symbolic/symbolic_reflection.py`
  - `brain/symbolic/symbolic_self_model.py`
  - `brain/utils/load_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/self_model.py`
**Imported by:** (2 files)
  - `brain/behavior/revise.py`
  - `brain/cognition/repair/auto_repair.py`

## `brain/cognition/reflection/reflect_on_cognition.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/error_router.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/log_reflection.py`
  - `brain/utils/num.py`
**Imported by:** (2 files)
  - `brain/cognition/reflection/meta_reflect.py`
  - `brain/cognition/repair/repair.py`

## `brain/cognition/reflection/reflect_on_cognition_schedule.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/symbolic/self_improvement.py`
  - `brain/symbolic/symbolic_cognition.py`
  - `brain/symbolic/symbolic_reflection.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/load_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/log_reflection.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/reflection/reflect_on_conversation.py`
**Imports:**
  - `brain/paths.py`
  - `brain/symbolic/crystallization.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/symbolic/symbolic_reflection.py`
  - `brain/utils/log.py`
  - `brain/utils/log_reflection.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/reflection/reflect_on_internal_agents.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/symbolic/crystallization.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/symbolic/symbolic_reflection.py`
  - `brain/utils/error_router.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/load_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/log_reflection.py`
  - `brain/utils/self_model.py`
**Imported by:** (1 files)
  - `brain/think/inner_loop.py`

## `brain/cognition/reflection/reflect_on_outcome.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/symbolic/symbolic_cognition.py`
  - `brain/symbolic/symbolic_reflection.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/load_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/log_reflection.py`
  - `brain/utils/self_model.py`
**Imported by:** (1 files)
  - `brain/cognition/reflection/meta_reflect.py`

## `brain/cognition/reflection/reflect_on_self_belief.py`
**Imports:**
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/affect/update_affect_state.py`
  - `brain/cog_memory/remember.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/maintenance/self_modeling.py`
  - `brain/cognition/planning/goals.py`
  - `brain/paths.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/symbolic/symbolic_cognition.py`
  - `brain/symbolic/symbolic_reflection.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/log_reflection.py`
  - `brain/utils/self_model.py`
**Imported by:** (1 files)
  - `brain/cognition/reflection/meta_reflect.py`

## `brain/cognition/reflection/rule_reflection.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/symbolic/symbolic_cognition.py`
  - `brain/symbolic/symbolic_reflection.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/load_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/log_reflection.py`
**Imported by:** (1 files)
  - `brain/cognition/reflection/meta_reflect.py`

## `brain/cognition/reflection/self_reflection.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/symbolic/crystallization.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/symbolic/symbolic_reflection.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/load_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/log_reflection.py`
**Imported by:** (1 files)
  - `brain/cognition/reflection/meta_reflect.py`

## `brain/cognition/reflection_metadata.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/dreaming/dream_cycle.py`

## `brain/cognition/regret.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/cognitive_cost.py`
  - `brain/paths.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/think/think_utils/finalize.py`

## `brain/cognition/repair/auto_repair.py`
**Imports:**
  - `brain/behavior/revise.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/reflection/meta_reflect.py`
  - `brain/paths.py`
  - `brain/registry/behavior_registry.py`
  - `brain/registry/cognition_registry.py`
  - `brain/think/think_utils/select_function.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/state_guard.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/cognition/repair/repair.py`
**Imports:**
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/cog_memory/remember.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/reflection/reflect_on_cognition.py`
  - `brain/paths.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/utils/feedback_log.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/load_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/log_reflection.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/reflection/meta_reflect.py`

## `brain/cognition/reward_calibrator.py`
**Imports:**
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/think/think_utils/finalize.py`

## `brain/cognition/rss_reader.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/rumination.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/think/think_module.py`

## `brain/cognition/sandbox.py`
**Imports:**
  - `brain/cog_memory/remember.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/self_model.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/search_own_files.py`
**Imports:**
  - `brain/agency/skills/grep_files.py`
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/perception/file_sense.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/perception/look_outward.py`
  - `brain/cognition/planning/pursue_goal.py`

## `brain/cognition/seek_novelty.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/cognition/perception/look_outward.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/self_extension.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/selfhood/fragmentation.py`
  - `brain/cognition/skill_synthesis.py`
  - `brain/paths.py`
  - `brain/registry/cognition_registry.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/skill_synthesis.py`

## `brain/cognition/self_generated/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/self_generated/autogenerated_thoughts.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/think/think_utils/finalize.py`

## `brain/cognition/selfhood/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/selfhood/autobiography.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/reconstruction.py`
  - `brain/cognition/selfhood/identity.py`
  - `brain/paths.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/utils/failure_counter.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/self_model.py`
**Imported by:** (4 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/selfhood/tensions.py`
  - `brain/cognition/terminal.py`

## `brain/cognition/selfhood/boundary_check.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/think/think_utils/action_gate.py`
  - `brain/think/think_utils/user_input.py`

## `brain/cognition/selfhood/ethics.py`
**Imports:**
  - `brain/paths.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/utils/core_utils.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/self_model.py`
  - `brain/utils/timing.py`
**Imported by:** (1 files)
  - `brain/cog_memory/long_memory.py`

## `brain/cognition/selfhood/fragmentation.py`
**Imports:**
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/selfhood/tensions.py`
  - `brain/paths.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/self_model.py`
**Imported by:** (2 files)
  - `brain/cognition/self_extension.py`
  - `brain/think/think_utils/finalize.py`

## `brain/cognition/selfhood/identity.py`
**Imports:**
  - `brain/affect/affect_summary.py`
  - `brain/affect/introspection.py`
  - `brain/cognition/selfhood/relationships.py`
  - `brain/paths.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/utils/failure_counter.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/runtime_ctx.py`
  - `brain/utils/self_model.py`
  - `brain/utils/timing.py`
**Imported by:** (4 files)
  - `brain/cognition/selfhood/autobiography.py`
  - `brain/cognition/selfhood/value_evolution.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/response_utils.py`

## `brain/cognition/selfhood/latent_identity.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/think/think_module.py`

## `brain/cognition/selfhood/person_detector.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/cognition/selfhood/relationships.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/utils/emotion_utils.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/cognition/selfhood/identity.py`
  - `brain/think/think_module.py`

## `brain/cognition/selfhood/self_model_conflicts.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/symbolic/symbolic_cognition.py`
  - `brain/symbolic/symbolic_reflection.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/self_model.py`
**Imported by:** (2 files)
  - `brain/cognition/reflection/meta_reflect.py`
  - `brain/think/think_module.py`

## `brain/cognition/selfhood/tensions.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/selfhood/autobiography.py`
  - `brain/paths.py`
  - `brain/utils/failure_counter.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/selfhood/fragmentation.py`

## `brain/cognition/selfhood/value_evolution.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/cognition/selfhood/identity.py`
  - `brain/paths.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/think/bandit/contextual_bandit.py`
  - `brain/utils/failure_counter.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/self_model.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/cognition/selfhood/values_check.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/paths.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/self_model.py`
  - `brain/utils/signal_utils.py`
**Imported by:** (1 files)
  - `brain/think/think_utils/user_input.py`

## `brain/cognition/skill_synthesis.py`
**Imports:**
  - `brain/cognition/knowledge_graph.py`
  - `brain/cognition/self_extension.py`
  - `brain/paths.py`
  - `brain/registry/cognition_registry.py`
  - `brain/think/sandbox_runner.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/agency/code_writer.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/self_extension.py`

## `brain/cognition/temporal_pressure.py`
**Imports:**
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/think/think_utils/action_gate.py`
  - `brain/think/think_utils/finalize.py`

## `brain/cognition/temporal_state.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/think/think_module.py`

## `brain/cognition/terminal.py`
**Imports:**
  - `brain/behavior/speak.py`
  - `brain/cognition/selfhood/autobiography.py`
  - `brain/paths.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/self_model.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/cognition/theory_of_mind.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/think/think_module.py`

## `brain/cognition/threads.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/paths.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
  - `brain/utils/signal_utils.py`
**Imported by:** (3 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/awaiting_response.py`
  - `brain/cognition/planning/goals.py`

## `brain/cognition/tools/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/tools/ask_llm.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/cognition/web_research.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/cognition/planning/pursue_goal.py`

## `brain/cognition/wikipedia_search.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/cognition/planning/pursue_goal.py`

## `brain/cognition/wonder.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/utils/log.py`
  - `brain/utils/signal_utils.py`
**Imported by:** (3 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/think/think_utils/user_input.py`

## `brain/cognition/world_model.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/symbolic/causal_graph.py`
  - `brain/symbolic/inference.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/self_model.py`
**Imported by:** (2 files)
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/reflection/meta_reflect.py`

## `brain/core/config/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/core/config/settings.py`
**Imports:**
  - `brain/utils/load_utils.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/utils/core_utils.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/llm_router.py`

## `brain/core/drive.py`
**Imports:**
  - `brain/affect/threat_detector.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/utils/log.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/core/manager.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/registry/cognition_registry.py`

## `brain/embodiment/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/embodiment/drive_engine.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/embodiment/setpoint_regulation.py`
**Imports:** *(none within project)*
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/health_monitor.py`

## `brain/embodiment/plasticity.py`
**Imports:**
  - `brain/affect/affect_learning.py`
  - `brain/paths.py`
  - `brain/registry/cognition_registry.py`
  - `brain/utils/json_utils.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/embodiment/sensory_stream.py`
**Imports:**
  - `brain/paths.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/embodiment/social_presence.py`
**Imports:**
  - `brain/paths.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/embodiment/subconscious.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/embodiment/system_presence.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/embodiment/world_model.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/cognition/perception/look_around.py`

## `brain/eval/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/eval/evaluator_daemon.py`
**Imports:**
  - `brain/eval/evaluator_wal.py`
  - `brain/paths.py`
  - `brain/think/bandit/contextual_bandit.py`
  - `brain/think/thought_stream.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/eval/evaluator_wal.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/eval/evaluator_daemon.py`

## `brain/events.py`
**Imports:** *(none within project)*
**Imported by:** (1 files)
  - `brain/alive_brain.py`

## `brain/goals_bridge.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/cognition/planning/goals.py`
  - `brain/paths.py`
  - `brain/utils/failure_counter.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/idea_service.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/memory_bridge.py`
**Imports:**
  - `brain/cog_memory/reconstruction.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/motivation/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/motivation/energy_orientation.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/think/think_module.py`
  - `brain/think/think_utils/select_function.py`

## `brain/motivation/substrate.py`
**Imports:**
  - `brain/cog_memory/long_memory.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/paths.py`
**Imports:** *(none within project)*
**Imported by:** (169 files)
  - `brain/ORRIN_loop.py`
  - `brain/affect/affect.py`
  - `brain/affect/affect_drift.py`
  - `brain/affect/affect_learning.py`
  - `brain/affect/consolidation.py`
  - `brain/affect/discovery.py`
  - `brain/affect/model.py`
  - `brain/affect/modes_and_affect.py`
  - `brain/affect/regulation.py`
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/affect/update_affect_state.py`
  - `brain/agency/code_writer.py`
  - `brain/agency/skills/save_note.py`
  - `brain/agency/tool_runner.py`
  - `brain/behavior/behavior_generation.py`
  - `brain/behavior/dynamic_loader.py`
  - `brain/behavior/pre_speak_check.py`
  - `brain/behavior/revise.py`
  - `brain/behavior/speak.py`
  - `brain/behavior/tools/sandbox.py`
  - `brain/behavior/tools/tool_executor.py`
  - `brain/behavior/tools/toolkit.py`
  - `brain/cog_memory/chat_log.py`
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/remember.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/ambient_thought.py`
  - `brain/cognition/associative_memory.py`
  - `brain/cognition/behavior.py`
  - `brain/cognition/body_sense.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/dreaming/episode_replay.py`
  - `brain/cognition/dreaming/semantic_extractor.py`
  - `brain/cognition/experimentation.py`
  - `brain/cognition/finetuning/finetune_pipeline.py`
  - `brain/cognition/habituation.py`
  - `brain/cognition/innovation/bootstrap.py`
  - `brain/cognition/innovation/evaluation.py`
  - `brain/cognition/innovation/exploration.py`
  - `brain/cognition/innovation/innovation.py`
  - `brain/cognition/intrinsic_goals.py`
  - `brain/cognition/knowledge_graph.py`
  - `brain/cognition/leave_note.py`
  - `brain/cognition/maintenance/self_modeling.py`
  - `brain/cognition/maintenance/self_review.py`
  - `brain/cognition/metacog.py`
  - `brain/cognition/mood.py`
  - `brain/cognition/mortality.py`
  - `brain/cognition/opinions.py`
  - `brain/cognition/perception/environment.py`
  - `brain/cognition/perception/look_around.py`
  - `brain/cognition/perception/look_outward.py`
  - `brain/cognition/planning/env_snapshot.py`
  - `brain/cognition/planning/evolution.py`
  - `brain/cognition/planning/goal_lifecycle.py`
  - `brain/cognition/planning/goals.py`
  - `brain/cognition/planning/introspection.py`
  - `brain/cognition/planning/motivations.py`
  - `brain/cognition/planning/pursue_goal.py`
  - `brain/cognition/planning/reflection.py`
  - `brain/cognition/planning/thinking_depth.py`
  - `brain/cognition/prediction.py`
  - `brain/cognition/privacy.py`
  - `brain/cognition/reflection/meta_reflect.py`
  - `brain/cognition/reflection/reflect_on_cognition.py`
  - `brain/cognition/reflection/reflect_on_cognition_schedule.py`
  - `brain/cognition/reflection/reflect_on_conversation.py`
  - `brain/cognition/reflection/reflect_on_outcome.py`
  - `brain/cognition/reflection/reflect_on_self_belief.py`
  - `brain/cognition/reflection/rule_reflection.py`
  - `brain/cognition/reflection/self_reflection.py`
  - `brain/cognition/reflection_metadata.py`
  - `brain/cognition/regret.py`
  - `brain/cognition/repair/auto_repair.py`
  - `brain/cognition/repair/repair.py`
  - `brain/cognition/reward_calibrator.py`
  - `brain/cognition/rss_reader.py`
  - `brain/cognition/rumination.py`
  - `brain/cognition/sandbox.py`
  - `brain/cognition/seek_novelty.py`
  - `brain/cognition/self_extension.py`
  - `brain/cognition/self_generated/autogenerated_thoughts.py`
  - `brain/cognition/selfhood/autobiography.py`
  - `brain/cognition/selfhood/boundary_check.py`
  - `brain/cognition/selfhood/ethics.py`
  - `brain/cognition/selfhood/fragmentation.py`
  - `brain/cognition/selfhood/identity.py`
  - `brain/cognition/selfhood/latent_identity.py`
  - `brain/cognition/selfhood/person_detector.py`
  - `brain/cognition/selfhood/relationships.py`
  - `brain/cognition/selfhood/self_model_conflicts.py`
  - `brain/cognition/selfhood/tensions.py`
  - `brain/cognition/selfhood/value_evolution.py`
  - `brain/cognition/selfhood/values_check.py`
  - `brain/cognition/skill_synthesis.py`
  - `brain/cognition/temporal_pressure.py`
  - `brain/cognition/temporal_state.py`
  - `brain/cognition/terminal.py`
  - `brain/cognition/theory_of_mind.py`
  - `brain/cognition/threads.py`
  - `brain/cognition/tools/ask_llm.py`
  - `brain/cognition/web_research.py`
  - `brain/cognition/wikipedia_search.py`
  - `brain/cognition/world_model.py`
  - `brain/core/manager.py`
  - `brain/embodiment/plasticity.py`
  - `brain/embodiment/sensory_stream.py`
  - `brain/embodiment/social_presence.py`
  - `brain/embodiment/subconscious.py`
  - `brain/embodiment/system_presence.py`
  - `brain/embodiment/world_model.py`
  - `brain/eval/evaluator_daemon.py`
  - `brain/eval/evaluator_wal.py`
  - `brain/goals_bridge.py`
  - `brain/memory_bridge.py`
  - `brain/motivation/energy_orientation.py`
  - `brain/motivation/substrate.py`
  - `brain/peers/architect.py`
  - `brain/peers/emotion_historian.py`
  - `brain/peers/goal_auditor.py`
  - `brain/peers/observer.py`
  - `brain/peers/peer_base.py`
  - `brain/peers/reward_auditor.py`
  - `brain/registry/behavior_registry.py`
  - `brain/registry/cognition_registry.py`
  - `brain/symbolic/analogy_engine.py`
  - `brain/symbolic/autonomous_experiment.py`
  - `brain/symbolic/benchmark.py`
  - `brain/symbolic/causal_graph.py`
  - `brain/symbolic/concept_formation.py`
  - `brain/symbolic/crystallization.py`
  - `brain/symbolic/embodied_actions.py`
  - `brain/symbolic/ground_truth.py`
  - `brain/symbolic/intrinsic_motivation.py`
  - `brain/symbolic/meta_rules.py`
  - `brain/symbolic/pattern_scorer.py`
  - `brain/symbolic/prediction_engine.py`
  - `brain/symbolic/progress_tracker.py`
  - `brain/symbolic/rule_abstraction.py`
  - `brain/symbolic/rule_compressor.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/symbolic/rule_forgetting.py`
  - `brain/symbolic/rule_synthesis.py`
  - `brain/symbolic/rule_verifier.py`
  - `brain/symbolic/self_improvement.py`
  - `brain/symbolic/symbolic_cognition.py`
  - `brain/symbolic/symbolic_dictionary.py`
  - `brain/symbolic/symbolic_dream.py`
  - `brain/symbolic/symbolic_reflection.py`
  - `brain/symbolic/symbolic_self_model.py`
  - `brain/symbolic/temporal_planner.py`
  - `brain/think/bandit/contextual_bandit.py`
  - `brain/think/depth_bandit.py`
  - `brain/think/loop_helpers.py`
  - `brain/think/meta_controller.py`
  - `brain/think/safe_runner.py`
  - `brain/think/speech_log.py`
  - `brain/think/speech_memory.py`
  - `brain/think/thalamus.py`
  - `brain/think/think_module.py`
  - `brain/think/think_utils/action_gate.py`
  - `brain/think/think_utils/dreams_emotional_logic.py`
  - `brain/think/think_utils/escalate.py`
  - `brain/think/think_utils/execute_cognitive_actions.py`
  - `brain/think/think_utils/finalize.py`
  - `brain/think/think_utils/reflect_on_directive.py`
  - `brain/think/think_utils/select_function.py`
  - `brain/think/think_utils/talk_policy.py`
  - `brain/think/think_utils/user_input.py`

## `brain/peers/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/peers/architect.py`
**Imports:**
  - `brain/cognition/perception/file_sense.py`
  - `brain/paths.py`
  - `brain/peers/peer_base.py`
**Imported by:** (1 files)
  - `brain/peers/peer_registry.py`

## `brain/peers/emotion_historian.py`
**Imports:**
  - `brain/paths.py`
  - `brain/peers/peer_base.py`
  - `brain/utils/json_utils.py`
**Imported by:** (1 files)
  - `brain/peers/peer_registry.py`

## `brain/peers/goal_auditor.py`
**Imports:**
  - `brain/paths.py`
  - `brain/peers/peer_base.py`
  - `brain/utils/json_utils.py`
**Imported by:** (1 files)
  - `brain/peers/peer_registry.py`

## `brain/peers/observer.py`
**Imports:**
  - `brain/cognition/perception/file_sense.py`
  - `brain/paths.py`
  - `brain/peers/peer_base.py`
  - `brain/utils/json_utils.py`
**Imported by:** (1 files)
  - `brain/peers/peer_registry.py`

## `brain/peers/peer_base.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/signal_utils.py`
**Imported by:** (5 files)
  - `brain/peers/architect.py`
  - `brain/peers/emotion_historian.py`
  - `brain/peers/goal_auditor.py`
  - `brain/peers/observer.py`
  - `brain/peers/reward_auditor.py`

## `brain/peers/peer_registry.py`
**Imports:**
  - `brain/peers/architect.py`
  - `brain/peers/emotion_historian.py`
  - `brain/peers/goal_auditor.py`
  - `brain/peers/observer.py`
  - `brain/peers/reward_auditor.py`
  - `brain/utils/get_cycle_count.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/peers/reward_auditor.py`
**Imports:**
  - `brain/paths.py`
  - `brain/peers/peer_base.py`
  - `brain/utils/json_utils.py`
**Imported by:** (1 files)
  - `brain/peers/peer_registry.py`

## `brain/registry/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/registry/behavior_registry.py`
**Imports:**
  - `brain/paths.py`
  - `brain/registry/utils.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (4 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/repair/auto_repair.py`
  - `brain/think/loop_helpers.py`
  - `brain/think/think_utils/action_gate.py`

## `brain/registry/cognition_registry.py`
**Imports:**
  - `brain/core/manager.py`
  - `brain/paths.py`
  - `brain/registry/utils.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (8 files)
  - `brain/ORRIN_loop.py`
  - `brain/agency/code_writer.py`
  - `brain/cognition/repair/auto_repair.py`
  - `brain/cognition/self_extension.py`
  - `brain/cognition/skill_synthesis.py`
  - `brain/embodiment/plasticity.py`
  - `brain/think/loop_helpers.py`
  - `brain/think/think_utils/select_function.py`

## `brain/registry/utils.py`
**Imports:** *(none within project)*
**Imported by:** (2 files)
  - `brain/registry/behavior_registry.py`
  - `brain/registry/cognition_registry.py`

## `brain/symbolic/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/symbolic/analogy_engine.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (7 files)
  - `brain/symbolic/autonomous_experiment.py`
  - `brain/symbolic/intrinsic_motivation.py`
  - `brain/symbolic/meta_rules.py`
  - `brain/symbolic/reasoning_router.py`
  - `brain/symbolic/symbolic_dream.py`
  - `brain/symbolic/symbolic_reflection.py`
  - `brain/symbolic/temporal_planner.py`

## `brain/symbolic/autonomous_experiment.py`
**Imports:**
  - `brain/paths.py`
  - `brain/symbolic/analogy_engine.py`
  - `brain/symbolic/causal_graph.py`
  - `brain/symbolic/crystallization.py`
  - `brain/symbolic/ground_truth.py`
  - `brain/symbolic/pattern_scorer.py`
  - `brain/symbolic/prediction_engine.py`
  - `brain/symbolic/progress_tracker.py`
  - `brain/symbolic/reasoning_router.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (4 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/symbolic/progress_tracker.py`
  - `brain/symbolic/symbolic_cognition.py`

## `brain/symbolic/benchmark.py`
**Imports:**
  - `brain/paths.py`
  - `brain/symbolic/reasoning_router.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/symbolic/progress_tracker.py`

## `brain/symbolic/causal_graph.py`
**Imports:**
  - `brain/paths.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (15 files)
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/knowledge_formation.py`
  - `brain/cognition/prediction.py`
  - `brain/cognition/world_model.py`
  - `brain/symbolic/autonomous_experiment.py`
  - `brain/symbolic/embodied_actions.py`
  - `brain/symbolic/prediction_engine.py`
  - `brain/symbolic/progress_tracker.py`
  - `brain/symbolic/reasoning_router.py`
  - `brain/symbolic/symbolic_cognition.py`
  - `brain/symbolic/symbolic_dream.py`
  - `brain/symbolic/symbolic_fluency.py`
  - `brain/symbolic/symbolic_reflection.py`
  - `brain/symbolic/symbolic_self_model.py`
  - `brain/symbolic/temporal_planner.py`

## `brain/symbolic/concept_formation.py`
**Imports:**
  - `brain/cognition/knowledge_graph.py`
  - `brain/paths.py`
  - `brain/symbolic/rule_abstraction.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/symbolic/progress_tracker.py`
  - `brain/symbolic/symbolic_self_model.py`

## `brain/symbolic/crystallization.py`
**Imports:**
  - `brain/paths.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (11 files)
  - `brain/affect/reflect_on_affect.py`
  - `brain/affect/reflect_on_affect_model.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/reflection/reflect_on_conversation.py`
  - `brain/cognition/reflection/reflect_on_internal_agents.py`
  - `brain/cognition/reflection/self_reflection.py`
  - `brain/symbolic/autonomous_experiment.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/symbolic/symbolic_reflection.py`
  - `brain/think/think_utils/reflect_on_directive.py`
  - `brain/utils/generate_response.py`

## `brain/symbolic/embodied_actions.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/symbolic/causal_graph.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/dreaming/dream_cycle.py`

## `brain/symbolic/ground_truth.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (7 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/symbolic/autonomous_experiment.py`
  - `brain/symbolic/rule_verifier.py`
  - `brain/symbolic/self_improvement.py`
  - `brain/symbolic/symbolic_self_model.py`
  - `brain/think/think_utils/action_gate.py`

## `brain/symbolic/inference.py`
**Imports:** *(none within project)*
**Imported by:** (1 files)
  - `brain/cognition/world_model.py`

## `brain/symbolic/intrinsic_motivation.py`
**Imports:**
  - `brain/paths.py`
  - `brain/symbolic/analogy_engine.py`
  - `brain/symbolic/prediction_engine.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/symbolic/symbolic_search.py`
  - `brain/symbolic/temporal_planner.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/ORRIN_loop.py`
  - `brain/symbolic/reasoning_router.py`
  - `brain/symbolic/symbolic_cognition.py`

## `brain/symbolic/llm_gate.py`
**Imports:**
  - `brain/symbolic/crystallization.py`
  - `brain/symbolic/meta_rules.py`
  - `brain/symbolic/progress_tracker.py`
  - `brain/symbolic/reasoning_router.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/log.py`
  - `brain/utils/token_meter.py`
**Imported by:** (23 files)
  - `brain/affect/reflect_on_affect.py`
  - `brain/affect/reflect_on_affect_model.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/maintenance/self_modeling.py`
  - `brain/cognition/planning/reflection.py`
  - `brain/cognition/reflection/reflect_on_conversation.py`
  - `brain/cognition/reflection/reflect_on_internal_agents.py`
  - `brain/cognition/reflection/reflect_on_outcome.py`
  - `brain/cognition/reflection/reflect_on_self_belief.py`
  - `brain/cognition/reflection/rule_reflection.py`
  - `brain/cognition/reflection/self_reflection.py`
  - `brain/cognition/repair/repair.py`
  - `brain/cognition/selfhood/autobiography.py`
  - `brain/cognition/selfhood/ethics.py`
  - `brain/cognition/selfhood/fragmentation.py`
  - `brain/cognition/selfhood/identity.py`
  - `brain/cognition/selfhood/relationships.py`
  - `brain/cognition/selfhood/self_model_conflicts.py`
  - `brain/cognition/selfhood/value_evolution.py`
  - `brain/cognition/selfhood/values_check.py`
  - `brain/embodiment/subconscious.py`
  - `brain/think/think_utils/action_gate.py`
  - `brain/think/think_utils/reflect_on_directive.py`

## `brain/symbolic/meta_rules.py`
**Imports:**
  - `brain/paths.py`
  - `brain/symbolic/analogy_engine.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (7 files)
  - `brain/symbolic/llm_gate.py`
  - `brain/symbolic/progress_tracker.py`
  - `brain/symbolic/reasoning_router.py`
  - `brain/symbolic/self_improvement.py`
  - `brain/symbolic/symbolic_cognition.py`
  - `brain/symbolic/symbolic_dream.py`
  - `brain/symbolic/symbolic_self_model.py`

## `brain/symbolic/pattern_scorer.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (6 files)
  - `brain/symbolic/autonomous_experiment.py`
  - `brain/symbolic/prediction_engine.py`
  - `brain/symbolic/progress_tracker.py`
  - `brain/symbolic/reasoning_router.py`
  - `brain/symbolic/rule_forgetting.py`
  - `brain/symbolic/rule_verifier.py`

## `brain/symbolic/prediction_engine.py`
**Imports:**
  - `brain/paths.py`
  - `brain/symbolic/causal_graph.py`
  - `brain/symbolic/pattern_scorer.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/symbolic/rule_verifier.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (8 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/prediction.py`
  - `brain/symbolic/autonomous_experiment.py`
  - `brain/symbolic/intrinsic_motivation.py`
  - `brain/symbolic/self_improvement.py`
  - `brain/symbolic/symbolic_cognition.py`
  - `brain/symbolic/symbolic_self_model.py`

## `brain/symbolic/progress_tracker.py`
**Imports:**
  - `brain/paths.py`
  - `brain/symbolic/autonomous_experiment.py`
  - `brain/symbolic/benchmark.py`
  - `brain/symbolic/causal_graph.py`
  - `brain/symbolic/concept_formation.py`
  - `brain/symbolic/meta_rules.py`
  - `brain/symbolic/pattern_scorer.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/symbolic/rule_forgetting.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/symbolic/autonomous_experiment.py`
  - `brain/symbolic/llm_gate.py`

## `brain/symbolic/reasoning_router.py`
**Imports:**
  - `brain/symbolic/analogy_engine.py`
  - `brain/symbolic/causal_graph.py`
  - `brain/symbolic/intrinsic_motivation.py`
  - `brain/symbolic/meta_rules.py`
  - `brain/symbolic/pattern_scorer.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/symbolic/rule_verifier.py`
  - `brain/symbolic/symbolic_search.py`
  - `brain/symbolic/symbolic_self_model.py`
  - `brain/utils/log.py`
**Imported by:** (5 files)
  - `brain/ORRIN_loop.py`
  - `brain/symbolic/autonomous_experiment.py`
  - `brain/symbolic/benchmark.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/utils/generate_response.py`

## `brain/symbolic/rule_abstraction.py`
**Imports:**
  - `brain/paths.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/symbolic/concept_formation.py`

## `brain/symbolic/rule_compressor.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/dreaming/dream_cycle.py`

## `brain/symbolic/rule_engine.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (25 files)
  - `brain/cognition/knowledge_formation.py`
  - `brain/cognition/reflection/reflect_on_outcome.py`
  - `brain/cognition/reflection/rule_reflection.py`
  - `brain/symbolic/autonomous_experiment.py`
  - `brain/symbolic/causal_graph.py`
  - `brain/symbolic/concept_formation.py`
  - `brain/symbolic/crystallization.py`
  - `brain/symbolic/embodied_actions.py`
  - `brain/symbolic/intrinsic_motivation.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/symbolic/prediction_engine.py`
  - `brain/symbolic/progress_tracker.py`
  - `brain/symbolic/reasoning_router.py`
  - `brain/symbolic/rule_abstraction.py`
  - `brain/symbolic/rule_forgetting.py`
  - `brain/symbolic/rule_synthesis.py`
  - `brain/symbolic/rule_verifier.py`
  - `brain/symbolic/self_improvement.py`
  - `brain/symbolic/symbolic_cognition.py`
  - `brain/symbolic/symbolic_dictionary.py`
  - `brain/symbolic/symbolic_dream.py`
  - `brain/symbolic/symbolic_fluency.py`
  - `brain/symbolic/symbolic_search.py`
  - `brain/symbolic/symbolic_self_model.py`
  - `brain/symbolic/temporal_planner.py`

## `brain/symbolic/rule_forgetting.py`
**Imports:**
  - `brain/cognition/knowledge_graph.py`
  - `brain/paths.py`
  - `brain/symbolic/pattern_scorer.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (3 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/symbolic/progress_tracker.py`

## `brain/symbolic/rule_synthesis.py`
**Imports:**
  - `brain/paths.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/cognition/dreaming/dream_cycle.py`

## `brain/symbolic/rule_verifier.py`
**Imports:**
  - `brain/paths.py`
  - `brain/symbolic/ground_truth.py`
  - `brain/symbolic/pattern_scorer.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (5 files)
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/symbolic/prediction_engine.py`
  - `brain/symbolic/reasoning_router.py`
  - `brain/symbolic/symbolic_self_model.py`
  - `brain/think/think_utils/finalize.py`

## `brain/symbolic/self_improvement.py`
**Imports:**
  - `brain/paths.py`
  - `brain/symbolic/ground_truth.py`
  - `brain/symbolic/meta_rules.py`
  - `brain/symbolic/prediction_engine.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/symbolic/symbolic_self_model.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (4 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/reflection/meta_reflect.py`
  - `brain/cognition/reflection/reflect_on_cognition_schedule.py`

## `brain/symbolic/symbolic_cognition.py`
**Imports:**
  - `brain/paths.py`
  - `brain/symbolic/autonomous_experiment.py`
  - `brain/symbolic/causal_graph.py`
  - `brain/symbolic/intrinsic_motivation.py`
  - `brain/symbolic/meta_rules.py`
  - `brain/symbolic/prediction_engine.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/symbolic/symbolic_self_model.py`
  - `brain/utils/log.py`
**Imported by:** (7 files)
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/maintenance/self_modeling.py`
  - `brain/cognition/reflection/reflect_on_cognition_schedule.py`
  - `brain/cognition/reflection/reflect_on_outcome.py`
  - `brain/cognition/reflection/reflect_on_self_belief.py`
  - `brain/cognition/reflection/rule_reflection.py`
  - `brain/cognition/selfhood/self_model_conflicts.py`

## `brain/symbolic/symbolic_dictionary.py`
**Imports:**
  - `brain/paths.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/symbolic/symbolic_fluency.py`

## `brain/symbolic/symbolic_dream.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/symbolic/analogy_engine.py`
  - `brain/symbolic/causal_graph.py`
  - `brain/symbolic/meta_rules.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/dreaming/dream_cycle.py`

## `brain/symbolic/symbolic_fluency.py`
**Imports:**
  - `brain/symbolic/causal_graph.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/symbolic/symbolic_dictionary.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/utils/generate_response.py`

## `brain/symbolic/symbolic_reflection.py`
**Imports:**
  - `brain/paths.py`
  - `brain/symbolic/analogy_engine.py`
  - `brain/symbolic/causal_graph.py`
  - `brain/symbolic/crystallization.py`
  - `brain/symbolic/symbolic_self_model.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (12 files)
  - `brain/affect/reflect_on_affect.py`
  - `brain/affect/reflect_on_affect_model.py`
  - `brain/cognition/reflection/meta_reflect.py`
  - `brain/cognition/reflection/reflect_on_cognition_schedule.py`
  - `brain/cognition/reflection/reflect_on_conversation.py`
  - `brain/cognition/reflection/reflect_on_internal_agents.py`
  - `brain/cognition/reflection/reflect_on_outcome.py`
  - `brain/cognition/reflection/reflect_on_self_belief.py`
  - `brain/cognition/reflection/rule_reflection.py`
  - `brain/cognition/reflection/self_reflection.py`
  - `brain/cognition/selfhood/self_model_conflicts.py`
  - `brain/think/think_utils/reflect_on_directive.py`

## `brain/symbolic/symbolic_search.py`
**Imports:**
  - `brain/cognition/knowledge_graph.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/symbolic/intrinsic_motivation.py`
  - `brain/symbolic/reasoning_router.py`

## `brain/symbolic/symbolic_self_model.py`
**Imports:**
  - `brain/paths.py`
  - `brain/symbolic/causal_graph.py`
  - `brain/symbolic/concept_formation.py`
  - `brain/symbolic/ground_truth.py`
  - `brain/symbolic/meta_rules.py`
  - `brain/symbolic/prediction_engine.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/symbolic/rule_verifier.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (6 files)
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/reflection/meta_reflect.py`
  - `brain/symbolic/reasoning_router.py`
  - `brain/symbolic/self_improvement.py`
  - `brain/symbolic/symbolic_cognition.py`
  - `brain/symbolic/symbolic_reflection.py`

## `brain/symbolic/temporal_planner.py`
**Imports:**
  - `brain/paths.py`
  - `brain/symbolic/analogy_engine.py`
  - `brain/symbolic/causal_graph.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/symbolic/intrinsic_motivation.py`

## `brain/think/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/think/attention_weights.py`
**Imports:**
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/think/thalamus.py`
  - `brain/think/think_utils/finalize.py`

## `brain/think/bandit/contextual_bandit.py`
**Imports:**
  - `brain/paths.py`
  - `brain/think/loop_helpers.py`
  - `brain/utils/json_utils.py`
**Imported by:** (6 files)
  - `brain/cognition/health_monitor.py`
  - `brain/cognition/innovation/evaluation.py`
  - `brain/cognition/metacog.py`
  - `brain/cognition/selfhood/value_evolution.py`
  - `brain/eval/evaluator_daemon.py`
  - `brain/think/think_utils/select_function.py`

## `brain/think/consciousness_trigger.py`
**Imports:**
  - `brain/utils/get_cycle_count.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/think/cycle_state.py`
**Imports:** *(none within project)*
**Imported by:** (2 files)
  - `brain/behavior/expression.py`
  - `brain/think/state_processor.py`

## `brain/think/depth_bandit.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/think/inner_loop.py`

## `brain/think/inner_loop.py`
**Imports:**
  - `brain/affect/affect_summary.py`
  - `brain/cognition/reflection/reflect_on_internal_agents.py`
  - `brain/think/depth_bandit.py`
  - `brain/think/meta_controller.py`
  - `brain/think/scratchpad.py`
  - `brain/think/simulate.py`
  - `brain/think/thought_stream.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/cognition/planning/pursue_goal.py`

## `brain/think/loop_helpers.py`
**Imports:**
  - `brain/affect/update_affect_state.py`
  - `brain/paths.py`
  - `brain/registry/behavior_registry.py`
  - `brain/registry/cognition_registry.py`
  - `brain/think/think_utils/action_gate.py`
  - `brain/think/think_utils/select_function.py`
  - `brain/utils/bandit.py`
  - `brain/utils/context_key.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/think/bandit/contextual_bandit.py`

## `brain/think/meta_controller.py`
**Imports:**
  - `brain/cognition/planning/thinking_depth.py`
  - `brain/paths.py`
  - `brain/think/simulate.py`
  - `brain/think/thought_stream.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/think/inner_loop.py`

## `brain/think/safe_runner.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/events.py`
  - `brain/utils/log.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/think/sandbox_runner.py`
**Imports:** *(none within project)*
**Imported by:** (4 files)
  - `brain/agency/code_writer.py`
  - `brain/behavior/revise.py`
  - `brain/behavior/tools/toolkit.py`
  - `brain/cognition/skill_synthesis.py`

## `brain/think/scratchpad.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/metacog.py`
**Imported by:** (4 files)
  - `brain/cognition/planning/pursue_goal.py`
  - `brain/think/inner_loop.py`
  - `brain/think/think_generate.py`
  - `brain/think/think_module.py`

## `brain/think/simulate.py`
**Imports:**
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
  - `brain/utils/token_meter.py`
**Imported by:** (2 files)
  - `brain/think/inner_loop.py`
  - `brain/think/meta_controller.py`

## `brain/think/speech_builder.py`
**Imports:**
  - `brain/think/speech_coherence.py`
  - `brain/think/speech_log.py`
**Imported by:** (1 files)
  - `brain/think/speech_generator.py`

## `brain/think/speech_coherence.py`
**Imports:** *(none within project)*
**Imported by:** (1 files)
  - `brain/think/speech_builder.py`

## `brain/think/speech_comprehension.py`
**Imports:** *(none within project)*
**Imported by:** (1 files)
  - `brain/think/speech_generator.py`

## `brain/think/speech_evaluator.py`
**Imports:**
  - `brain/think/speech_log.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/think/think_utils/user_input.py`

## `brain/think/speech_generator.py`
**Imports:**
  - `brain/think/speech_builder.py`
  - `brain/think/speech_comprehension.py`
  - `brain/think/speech_log.py`
  - `brain/think/speech_memory.py`
  - `brain/think/speech_planner.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/behavior/speech_gate.py`

## `brain/think/speech_log.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (4 files)
  - `brain/think/speech_builder.py`
  - `brain/think/speech_evaluator.py`
  - `brain/think/speech_generator.py`
  - `brain/think/think_utils/talk_policy.py`

## `brain/think/speech_memory.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
**Imported by:** (1 files)
  - `brain/think/speech_generator.py`

## `brain/think/speech_planner.py`
**Imports:** *(none within project)*
**Imported by:** (1 files)
  - `brain/think/speech_generator.py`

## `brain/think/state_graph.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/think/state_processor.py`
**Imports:**
  - `brain/affect/affect_summary.py`
  - `brain/cog_memory/reconstruction.py`
  - `brain/think/cycle_state.py`
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/think/think_module.py`
  - `brain/think/think_utils/action_gate.py`

## `brain/think/thalamus.py`
**Imports:**
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/cog_memory/long_memory.py`
  - `brain/cognition/attention.py`
  - `brain/paths.py`
  - `brain/think/attention_weights.py`
  - `brain/think/think_utils/user_input.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/knowledge_utils.py`
  - `brain/utils/load_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/signal_utils.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/think/think_generate.py`
**Imports:**
  - `brain/think/scratchpad.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/think/think_module.py`
**Imports:**
  - `brain/affect/affect_learning.py`
  - `brain/affect/introspection.py`
  - `brain/behavior/speak.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/ambient_thought.py`
  - `brain/cognition/concept_memory.py`
  - `brain/cognition/knowledge_graph.py`
  - `brain/cognition/metacog.py`
  - `brain/cognition/rumination.py`
  - `brain/cognition/selfhood/latent_identity.py`
  - `brain/cognition/selfhood/relationships.py`
  - `brain/cognition/selfhood/self_model_conflicts.py`
  - `brain/cognition/temporal_state.py`
  - `brain/cognition/theory_of_mind.py`
  - `brain/motivation/energy_orientation.py`
  - `brain/paths.py`
  - `brain/think/scratchpad.py`
  - `brain/think/state_processor.py`
  - `brain/think/think_utils/action_gate.py`
  - `brain/think/think_utils/dreams_emotional_logic.py`
  - `brain/think/think_utils/execute_cognitive_actions.py`
  - `brain/think/think_utils/finalize.py`
  - `brain/think/think_utils/reflect_on_directive.py`
  - `brain/think/think_utils/select_function.py`
  - `brain/think/thought_stream.py`
  - `brain/utils/emotion_utils.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/manage_cycle_count.py`
  - `brain/utils/runtime_ctx.py`
**Imported by:** (1 files)
  - `brain/ORRIN_loop.py`

## `brain/think/think_utils/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/think/think_utils/action_gate.py`
**Imports:**
  - `brain/affect/affect_learning.py`
  - `brain/affect/reward_signals/action_reward_ema.py`
  - `brain/affect/reward_signals/resource_deficit.py`
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/behavior/behavior_generation.py`
  - `brain/behavior/expression.py`
  - `brain/behavior/pre_speak_check.py`
  - `brain/behavior/speak.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/behavior.py`
  - `brain/cognition/cognitive_cost.py`
  - `brain/cognition/planning/goals.py`
  - `brain/cognition/selfhood/boundary_check.py`
  - `brain/cognition/temporal_pressure.py`
  - `brain/paths.py`
  - `brain/registry/behavior_registry.py`
  - `brain/symbolic/ground_truth.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/think/state_processor.py`
  - `brain/think/think_utils/escalate.py`
  - `brain/think/think_utils/talk_policy.py`
  - `brain/utils/emotion_utils.py`
  - `brain/utils/goals.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/signal_utils.py`
**Imported by:** (3 files)
  - `brain/ORRIN_loop.py`
  - `brain/think/loop_helpers.py`
  - `brain/think/think_module.py`

## `brain/think/think_utils/dreams_emotional_logic.py`
**Imports:**
  - `brain/affect/affect_drift.py`
  - `brain/affect/threat_detector.py`
  - `brain/affect/apply_affective_feedback.py`
  - `brain/affect/reflect_on_affect.py`
  - `brain/affect/reward_signals/resource_deficit.py`
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/affect/update_affect_state.py`
  - `brain/behavior/behavior_generation.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/dreaming.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
**Imported by:** (1 files)
  - `brain/think/think_module.py`

## `brain/think/think_utils/escalate.py`
**Imports:**
  - `brain/paths.py`
  - `brain/utils/generate_response.py`
**Imported by:** (2 files)
  - `brain/think/think_utils/action_gate.py`
  - `brain/think/think_utils/finalize.py`

## `brain/think/think_utils/execute_cognitive_actions.py`
**Imports:**
  - `brain/affect/reward_signals/action_reward_ema.py`
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/self_model.py`
**Imported by:** (1 files)
  - `brain/think/think_module.py`

## `brain/think/think_utils/finalize.py`
**Imports:**
  - `brain/affect/regulation.py`
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/affect/update_affect_state.py`
  - `brain/behavior/tools/toolkit.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/associative_memory.py`
  - `brain/cognition/cognitive_cost.py`
  - `brain/cognition/habituation.py`
  - `brain/cognition/mood.py`
  - `brain/cognition/mortality.py`
  - `brain/cognition/opinions.py`
  - `brain/cognition/perception/environment.py`
  - `brain/cognition/planning/motivations.py`
  - `brain/cognition/regret.py`
  - `brain/cognition/reward_calibrator.py`
  - `brain/cognition/self_generated/autogenerated_thoughts.py`
  - `brain/cognition/selfhood/fragmentation.py`
  - `brain/cognition/temporal_pressure.py`
  - `brain/paths.py`
  - `brain/symbolic/rule_verifier.py`
  - `brain/think/attention_weights.py`
  - `brain/think/think_utils/escalate.py`
  - `brain/utils/events.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/timing.py`
  - `brain/utils/trace_buffer.py`
**Imported by:** (1 files)
  - `brain/think/think_module.py`

## `brain/think/think_utils/reflect_on_directive.py`
**Imports:**
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/paths.py`
  - `brain/symbolic/crystallization.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/symbolic/symbolic_reflection.py`
  - `brain/utils/goals.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/knowledge_utils.py`
**Imported by:** (1 files)
  - `brain/think/think_module.py`

## `brain/think/think_utils/select_function.py`
**Imports:**
  - `brain/affect/modes_and_affect.py`
  - `brain/cognition/emotion_routing.py`
  - `brain/cognition/goal_competition.py`
  - `brain/cognition/inhibition.py`
  - `brain/motivation/energy_orientation.py`
  - `brain/paths.py`
  - `brain/registry/cognition_registry.py`
  - `brain/think/bandit/contextual_bandit.py`
  - `brain/utils/goals.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
**Imported by:** (5 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/experimentation.py`
  - `brain/cognition/repair/auto_repair.py`
  - `brain/think/loop_helpers.py`
  - `brain/think/think_module.py`

## `brain/think/think_utils/talk_policy.py`
**Imports:**
  - `brain/behavior/speak.py`
  - `brain/behavior/speech_gate.py`
  - `brain/paths.py`
  - `brain/think/speech_log.py`
  - `brain/utils/log.py`
**Imported by:** (1 files)
  - `brain/think/think_utils/action_gate.py`

## `brain/think/think_utils/user_input.py`
**Imports:**
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/cog_memory/chat_log.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/comprehension.py`
  - `brain/cognition/contagion.py`
  - `brain/cognition/selfhood/boundary_check.py`
  - `brain/cognition/selfhood/values_check.py`
  - `brain/cognition/wonder.py`
  - `brain/paths.py`
  - `brain/think/speech_evaluator.py`
  - `brain/utils/log.py`
  - `brain/utils/self_model.py`
  - `brain/utils/signal_utils.py`
  - `brain/utils/timing.py`
**Imported by:** (1 files)
  - `brain/think/thalamus.py`

## `brain/think/thought_stream.py`
**Imports:** *(none within project)*
**Imported by:** (4 files)
  - `brain/eval/evaluator_daemon.py`
  - `brain/think/inner_loop.py`
  - `brain/think/meta_controller.py`
  - `brain/think/think_module.py`

## `brain/utils/__init__.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/utils/alive_brain.py`
**Imports:**
  - `brain/utils/sys_events.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/utils/append.py`
**Imports:**
  - `brain/utils/log.py`
**Imported by:** (6 files)
  - `brain/behavior/revise.py`
  - `brain/cog_memory/chat_log.py`
  - `brain/cognition/innovation/exploration.py`
  - `brain/cognition/innovation/innovation.py`
  - `brain/cognition/maintenance/self_review.py`
  - `brain/utils/log_reflection.py`

## `brain/utils/bandit.py`
**Imports:**
  - `brain/utils/json_utils.py`
  - `brain/utils/paths.py`
**Imported by:** (1 files)
  - `brain/think/loop_helpers.py`

## `brain/utils/checkpoint.py`
**Imports:**
  - `brain/utils/json_utils.py`
  - `brain/utils/paths.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/utils/code_validation.py`
**Imports:** *(none within project)*
**Imported by:** (1 files)
  - `brain/behavior/revise.py`

## `brain/utils/coerce_to_string.py`
**Imports:** *(none within project)*
**Imported by:** (4 files)
  - `brain/affect/affect.py`
  - `brain/affect/reflect_on_affect.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/response_utils.py`

## `brain/utils/context_key.py`
**Imports:** *(none within project)*
**Imported by:** (1 files)
  - `brain/think/loop_helpers.py`

## `brain/utils/core_utils.py`
**Imports:**
  - `brain/core/config/settings.py`
  - `brain/utils/emotion_utils.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/log.py`
  - `brain/utils/paths.py`
**Imported by:** (3 files)
  - `brain/behavior/tools/toolkit.py`
  - `brain/cognition/innovation/exploration.py`
  - `brain/cognition/selfhood/ethics.py`

## `brain/utils/embedder.py`
**Imports:** *(none within project)*
**Imported by:** (4 files)
  - `brain/cog_memory/remember.py`
  - `brain/cog_memory/summarize_w_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/utils/knowledge_utils.py`

## `brain/utils/emotion_utils.py`
**Imports:**
  - `brain/affect/model.py`
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/paths.py`
  - `brain/utils/self_model.py`
**Imported by:** (7 files)
  - `brain/ORRIN_loop.py`
  - `brain/affect/threat_detector.py`
  - `brain/affect/apply_affective_feedback.py`
  - `brain/cognition/selfhood/relationships.py`
  - `brain/think/think_module.py`
  - `brain/think/think_utils/action_gate.py`
  - `brain/utils/core_utils.py`

## `brain/utils/emotional_feedback.py`
**Imports:**
  - `brain/cog_memory/working_memory.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/paths.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/utils/emotional_response.py`
**Imports:**
  - `brain/affect/threat_detector.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/llm_router.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/utils/error.py`
**Imports:**
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/path_redact.py`
  - `brain/utils/paths.py`
**Imported by:** (1 files)
  - `brain/utils/error_router.py`

## `brain/utils/error_router.py`
**Imports:**
  - `brain/utils/error.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/path_redact.py`
  - `brain/utils/paths.py`
**Imported by:** (4 files)
  - `brain/ORRIN_loop.py`
  - `brain/behavior/tools/toolkit.py`
  - `brain/cognition/reflection/reflect_on_cognition.py`
  - `brain/cognition/reflection/reflect_on_internal_agents.py`

## `brain/utils/events.py`
**Imports:**
  - `brain/utils/paths.py`
**Imported by:** (3 files)
  - `brain/behavior/tools/tool_executor.py`
  - `brain/think/safe_runner.py`
  - `brain/think/think_utils/finalize.py`

## `brain/utils/events_miner.py`
**Imports:**
  - `brain/utils/paths.py`
**Imported by:** (1 files)
  - `brain/cognition/maintenance/self_review.py`

## `brain/utils/failure_counter.py`
**Imports:**
  - `brain/utils/paths.py`
**Imported by:** (10 files)
  - `brain/ORRIN_loop.py`
  - `brain/agency/tool_runner.py`
  - `brain/cognition/perception/look_outward.py`
  - `brain/cognition/planning/env_snapshot.py`
  - `brain/cognition/planning/evolution.py`
  - `brain/cognition/selfhood/autobiography.py`
  - `brain/cognition/selfhood/identity.py`
  - `brain/cognition/selfhood/tensions.py`
  - `brain/cognition/selfhood/value_evolution.py`
  - `brain/goals_bridge.py`

## `brain/utils/feedback_log.py`
**Imports:**
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/paths.py`
**Imported by:** (1 files)
  - `brain/cognition/repair/repair.py`

## `brain/utils/generate_response.py`
**Imports:**
  - `brain/cognition/selfhood/identity.py`
  - `brain/core/config/settings.py`
  - `brain/symbolic/crystallization.py`
  - `brain/symbolic/reasoning_router.py`
  - `brain/symbolic/symbolic_fluency.py`
  - `brain/utils/coerce_to_string.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/paths.py`
  - `brain/utils/self_model.py`
  - `brain/utils/token_meter.py`
**Imported by:** (39 files)
  - `brain/affect/affect.py`
  - `brain/affect/affect_drift.py`
  - `brain/affect/discovery.py`
  - `brain/agency/code_writer.py`
  - `brain/behavior/behavior_generation.py`
  - `brain/behavior/revise.py`
  - `brain/behavior/speech_gate.py`
  - `brain/behavior/speech_pipeline.py`
  - `brain/behavior/tools/tool_executor.py`
  - `brain/behavior/tools/toolkit.py`
  - `brain/cog_memory/chat_log.py`
  - `brain/cognition/experimentation.py`
  - `brain/cognition/innovation/bootstrap.py`
  - `brain/cognition/innovation/evaluation.py`
  - `brain/cognition/innovation/exploration.py`
  - `brain/cognition/innovation/innovation.py`
  - `brain/cognition/intrinsic_goals.py`
  - `brain/cognition/knowledge_graph.py`
  - `brain/cognition/mortality.py`
  - `brain/cognition/opinions.py`
  - `brain/cognition/planning/evolution.py`
  - `brain/cognition/planning/goals.py`
  - `brain/cognition/planning/introspection.py`
  - `brain/cognition/planning/motivations.py`
  - `brain/cognition/planning/pursue_goal.py`
  - `brain/cognition/regret.py`
  - `brain/cognition/sandbox.py`
  - `brain/cognition/self_extension.py`
  - `brain/cognition/self_generated/autogenerated_thoughts.py`
  - `brain/cognition/skill_synthesis.py`
  - `brain/cognition/terminal.py`
  - `brain/cognition/threads.py`
  - `brain/cognition/tools/ask_llm.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/think/think_utils/escalate.py`
  - `brain/utils/core_utils.py`
  - `brain/utils/emotional_response.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/response_utils.py`

## `brain/utils/get_cycle_count.py`
**Imports:**
  - `brain/utils/paths.py`
**Imported by:** (3 files)
  - `brain/ORRIN_loop.py`
  - `brain/peers/peer_registry.py`
  - `brain/think/consciousness_trigger.py`

## `brain/utils/goals.py`
**Imports:** *(none within project)*
**Imported by:** (4 files)
  - `brain/behavior/behavior_generation.py`
  - `brain/think/think_utils/action_gate.py`
  - `brain/think/think_utils/reflect_on_directive.py`
  - `brain/think/think_utils/select_function.py`

## `brain/utils/goals_feed.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/utils/hash_utils.py`
**Imports:**
  - `brain/utils/log.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/utils/json_utils.py`
**Imports:**
  - `brain/utils/log.py`
**Imported by:** (178 files)
  - `brain/ORRIN_loop.py`
  - `brain/affect/affect.py`
  - `brain/affect/affect_drift.py`
  - `brain/affect/affect_learning.py`
  - `brain/affect/consolidation.py`
  - `brain/affect/discovery.py`
  - `brain/affect/model.py`
  - `brain/affect/modes_and_affect.py`
  - `brain/affect/regulation.py`
  - `brain/affect/reward_signals/action_reward_ema.py`
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/affect/update_affect_state.py`
  - `brain/agency/tool_runner.py`
  - `brain/behavior/behavior_generation.py`
  - `brain/behavior/expression.py`
  - `brain/behavior/pre_speak_check.py`
  - `brain/behavior/revise.py`
  - `brain/behavior/speak.py`
  - `brain/behavior/tools/tool_executor.py`
  - `brain/behavior/tools/toolkit.py`
  - `brain/cog_memory/chat_log.py`
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/remember.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/ambient_thought.py`
  - `brain/cognition/associative_memory.py`
  - `brain/cognition/body_sense.py`
  - `brain/cognition/comprehension.py`
  - `brain/cognition/concept_memory.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/dreaming/episode_replay.py`
  - `brain/cognition/dreaming/semantic_extractor.py`
  - `brain/cognition/experimentation.py`
  - `brain/cognition/finetuning/finetune_pipeline.py`
  - `brain/cognition/habituation.py`
  - `brain/cognition/health_monitor.py`
  - `brain/cognition/innovation/bootstrap.py`
  - `brain/cognition/innovation/evaluation.py`
  - `brain/cognition/innovation/exploration.py`
  - `brain/cognition/innovation/innovation.py`
  - `brain/cognition/intrinsic_goals.py`
  - `brain/cognition/knowledge_graph.py`
  - `brain/cognition/leave_note.py`
  - `brain/cognition/maintenance/self_modeling.py`
  - `brain/cognition/maintenance/self_review.py`
  - `brain/cognition/metacog.py`
  - `brain/cognition/mood.py`
  - `brain/cognition/mortality.py`
  - `brain/cognition/opinions.py`
  - `brain/cognition/perception/environment.py`
  - `brain/cognition/perception/look_around.py`
  - `brain/cognition/perception/look_outward.py`
  - `brain/cognition/planning/evolution.py`
  - `brain/cognition/planning/goal_lifecycle.py`
  - `brain/cognition/planning/goals.py`
  - `brain/cognition/planning/introspection.py`
  - `brain/cognition/planning/motivations.py`
  - `brain/cognition/planning/pursue_goal.py`
  - `brain/cognition/planning/reflection.py`
  - `brain/cognition/planning/thinking_depth.py`
  - `brain/cognition/prediction.py`
  - `brain/cognition/privacy.py`
  - `brain/cognition/reflection/reflect_on_cognition.py`
  - `brain/cognition/reflection/reflect_on_cognition_schedule.py`
  - `brain/cognition/reflection/reflect_on_internal_agents.py`
  - `brain/cognition/reflection/reflect_on_outcome.py`
  - `brain/cognition/reflection/reflect_on_self_belief.py`
  - `brain/cognition/reflection/rule_reflection.py`
  - `brain/cognition/reflection/self_reflection.py`
  - `brain/cognition/reflection_metadata.py`
  - `brain/cognition/regret.py`
  - `brain/cognition/repair/auto_repair.py`
  - `brain/cognition/repair/repair.py`
  - `brain/cognition/reward_calibrator.py`
  - `brain/cognition/rss_reader.py`
  - `brain/cognition/rumination.py`
  - `brain/cognition/sandbox.py`
  - `brain/cognition/seek_novelty.py`
  - `brain/cognition/self_extension.py`
  - `brain/cognition/self_generated/autogenerated_thoughts.py`
  - `brain/cognition/selfhood/autobiography.py`
  - `brain/cognition/selfhood/boundary_check.py`
  - `brain/cognition/selfhood/ethics.py`
  - `brain/cognition/selfhood/fragmentation.py`
  - `brain/cognition/selfhood/identity.py`
  - `brain/cognition/selfhood/latent_identity.py`
  - `brain/cognition/selfhood/person_detector.py`
  - `brain/cognition/selfhood/relationships.py`
  - `brain/cognition/selfhood/self_model_conflicts.py`
  - `brain/cognition/selfhood/tensions.py`
  - `brain/cognition/selfhood/value_evolution.py`
  - `brain/cognition/selfhood/values_check.py`
  - `brain/cognition/skill_synthesis.py`
  - `brain/cognition/temporal_pressure.py`
  - `brain/cognition/temporal_state.py`
  - `brain/cognition/terminal.py`
  - `brain/cognition/theory_of_mind.py`
  - `brain/cognition/threads.py`
  - `brain/cognition/tools/ask_llm.py`
  - `brain/cognition/web_research.py`
  - `brain/cognition/wikipedia_search.py`
  - `brain/cognition/world_model.py`
  - `brain/embodiment/plasticity.py`
  - `brain/embodiment/subconscious.py`
  - `brain/embodiment/system_presence.py`
  - `brain/embodiment/world_model.py`
  - `brain/eval/evaluator_daemon.py`
  - `brain/goals_bridge.py`
  - `brain/memory_bridge.py`
  - `brain/motivation/energy_orientation.py`
  - `brain/motivation/substrate.py`
  - `brain/peers/emotion_historian.py`
  - `brain/peers/goal_auditor.py`
  - `brain/peers/observer.py`
  - `brain/peers/peer_base.py`
  - `brain/peers/reward_auditor.py`
  - `brain/registry/behavior_registry.py`
  - `brain/registry/cognition_registry.py`
  - `brain/symbolic/analogy_engine.py`
  - `brain/symbolic/autonomous_experiment.py`
  - `brain/symbolic/benchmark.py`
  - `brain/symbolic/causal_graph.py`
  - `brain/symbolic/concept_formation.py`
  - `brain/symbolic/crystallization.py`
  - `brain/symbolic/embodied_actions.py`
  - `brain/symbolic/ground_truth.py`
  - `brain/symbolic/intrinsic_motivation.py`
  - `brain/symbolic/meta_rules.py`
  - `brain/symbolic/pattern_scorer.py`
  - `brain/symbolic/prediction_engine.py`
  - `brain/symbolic/progress_tracker.py`
  - `brain/symbolic/rule_abstraction.py`
  - `brain/symbolic/rule_compressor.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/symbolic/rule_forgetting.py`
  - `brain/symbolic/rule_synthesis.py`
  - `brain/symbolic/rule_verifier.py`
  - `brain/symbolic/self_improvement.py`
  - `brain/symbolic/symbolic_dictionary.py`
  - `brain/symbolic/symbolic_dream.py`
  - `brain/symbolic/symbolic_reflection.py`
  - `brain/symbolic/symbolic_self_model.py`
  - `brain/symbolic/temporal_planner.py`
  - `brain/think/attention_weights.py`
  - `brain/think/bandit/contextual_bandit.py`
  - `brain/think/depth_bandit.py`
  - `brain/think/loop_helpers.py`
  - `brain/think/meta_controller.py`
  - `brain/think/speech_log.py`
  - `brain/think/speech_memory.py`
  - `brain/think/thalamus.py`
  - `brain/think/think_module.py`
  - `brain/think/think_utils/action_gate.py`
  - `brain/think/think_utils/dreams_emotional_logic.py`
  - `brain/think/think_utils/execute_cognitive_actions.py`
  - `brain/think/think_utils/finalize.py`
  - `brain/think/think_utils/reflect_on_directive.py`
  - `brain/think/think_utils/select_function.py`
  - `brain/utils/bandit.py`
  - `brain/utils/checkpoint.py`
  - `brain/utils/core_utils.py`
  - `brain/utils/emotion_utils.py`
  - `brain/utils/emotional_feedback.py`
  - `brain/utils/error.py`
  - `brain/utils/error_router.py`
  - `brain/utils/feedback_log.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/knowledge_utils.py`
  - `brain/utils/llm_router.py`
  - `brain/utils/load_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/manage_cycle_count.py`
  - `brain/utils/memory_graph.py`
  - `brain/utils/response_utils.py`
  - `brain/utils/self_model.py`
  - `brain/utils/state.py`
  - `brain/utils/state_guard.py`
  - `brain/utils/summarizers.py`

## `brain/utils/knowledge_utils.py`
**Imports:**
  - `brain/utils/embedder.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/paths.py`
**Imported by:** (2 files)
  - `brain/think/thalamus.py`
  - `brain/think/think_utils/reflect_on_directive.py`

## `brain/utils/linting.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/utils/llm_router.py`
**Imports:**
  - `brain/core/config/settings.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
**Imported by:** (29 files)
  - `brain/behavior/revise.py`
  - `brain/behavior/speech_gate.py`
  - `brain/behavior/tools/tool_executor.py`
  - `brain/cog_memory/chat_log.py`
  - `brain/cognition/comprehension.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/experimentation.py`
  - `brain/cognition/innovation/bootstrap.py`
  - `brain/cognition/innovation/evaluation.py`
  - `brain/cognition/innovation/exploration.py`
  - `brain/cognition/innovation/innovation.py`
  - `brain/cognition/intrinsic_goals.py`
  - `brain/cognition/knowledge_graph.py`
  - `brain/cognition/opinions.py`
  - `brain/cognition/planning/evolution.py`
  - `brain/cognition/planning/introspection.py`
  - `brain/cognition/planning/motivations.py`
  - `brain/cognition/planning/pursue_goal.py`
  - `brain/cognition/regret.py`
  - `brain/cognition/sandbox.py`
  - `brain/cognition/self_extension.py`
  - `brain/cognition/self_generated/autogenerated_thoughts.py`
  - `brain/cognition/skill_synthesis.py`
  - `brain/cognition/threads.py`
  - `brain/think/inner_loop.py`
  - `brain/think/simulate.py`
  - `brain/think/think_generate.py`
  - `brain/utils/core_utils.py`
  - `brain/utils/emotional_response.py`

## `brain/utils/load_utils.py`
**Imports:**
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/paths.py`
**Imported by:** (13 files)
  - `brain/ORRIN_loop.py`
  - `brain/affect/reflect_on_affect.py`
  - `brain/affect/reflect_on_affect_model.py`
  - `brain/cognition/planning/reflection.py`
  - `brain/cognition/reflection/meta_reflect.py`
  - `brain/cognition/reflection/reflect_on_cognition_schedule.py`
  - `brain/cognition/reflection/reflect_on_internal_agents.py`
  - `brain/cognition/reflection/reflect_on_outcome.py`
  - `brain/cognition/reflection/rule_reflection.py`
  - `brain/cognition/reflection/self_reflection.py`
  - `brain/cognition/repair/repair.py`
  - `brain/core/config/settings.py`
  - `brain/think/thalamus.py`

## `brain/utils/log.py`
**Imports:**
  - `brain/utils/json_utils.py`
  - `brain/utils/path_redact.py`
  - `brain/utils/paths.py`
**Imported by:** (208 files)
  - `brain/ORRIN_loop.py`
  - `brain/affect/affect.py`
  - `brain/affect/affect_buffer.py`
  - `brain/affect/affect_drift.py`
  - `brain/affect/threat_detector.py`
  - `brain/affect/stagnation_signal_escalation.py`
  - `brain/affect/consolidation.py`
  - `brain/affect/discovery.py`
  - `brain/affect/integration_lag.py`
  - `brain/affect/model.py`
  - `brain/affect/modes_and_affect.py`
  - `brain/affect/reflect_on_affect.py`
  - `brain/affect/reflect_on_affect_model.py`
  - `brain/affect/regulation.py`
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/affect/reward_signals/reward_spike.py`
  - `brain/affect/update_affect_state.py`
  - `brain/agency/code_writer.py`
  - `brain/agency/skills/grep_files.py`
  - `brain/agency/skills/list_directory.py`
  - `brain/agency/skills/notify_user.py`
  - `brain/agency/skills/save_note.py`
  - `brain/agency/skills/search_files.py`
  - `brain/agency/tool_runner.py`
  - `brain/behavior/behavior_generation.py`
  - `brain/behavior/dynamic_loader.py`
  - `brain/behavior/expression.py`
  - `brain/behavior/pre_speak_check.py`
  - `brain/behavior/revise.py`
  - `brain/behavior/speak.py`
  - `brain/behavior/speech_gate.py`
  - `brain/behavior/speech_pipeline.py`
  - `brain/behavior/tools/tool_executor.py`
  - `brain/behavior/tools/toolkit.py`
  - `brain/cog_memory/chat_log.py`
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/remember.py`
  - `brain/cog_memory/summarize_w_memory.py`
  - `brain/cog_memory/working_memory.py`
  - `brain/cognition/ambient_thought.py`
  - `brain/cognition/associative_memory.py`
  - `brain/cognition/awaiting_response.py`
  - `brain/cognition/behavior.py`
  - `brain/cognition/behavioral_adaptation.py`
  - `brain/cognition/body_sense.py`
  - `brain/cognition/cognitive_cost.py`
  - `brain/cognition/comprehension.py`
  - `brain/cognition/contagion.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/dreaming/episode_replay.py`
  - `brain/cognition/dreaming/semantic_extractor.py`
  - `brain/cognition/experimentation.py`
  - `brain/cognition/finetuning/finetune_pipeline.py`
  - `brain/cognition/goal_competition.py`
  - `brain/cognition/habituation.py`
  - `brain/cognition/health_monitor.py`
  - `brain/cognition/inhibition.py`
  - `brain/cognition/innovation/bootstrap.py`
  - `brain/cognition/innovation/evaluation.py`
  - `brain/cognition/innovation/exploration.py`
  - `brain/cognition/innovation/innovation.py`
  - `brain/cognition/intrinsic_goals.py`
  - `brain/cognition/knowledge_formation.py`
  - `brain/cognition/knowledge_graph.py`
  - `brain/cognition/leave_note.py`
  - `brain/cognition/local_search_signal.py`
  - `brain/cognition/maintenance/self_modeling.py`
  - `brain/cognition/maintenance/self_review.py`
  - `brain/cognition/metacog.py`
  - `brain/cognition/mood.py`
  - `brain/cognition/mortality.py`
  - `brain/cognition/opinions.py`
  - `brain/cognition/perception/environment.py`
  - `brain/cognition/perception/fs_perception.py`
  - `brain/cognition/perception/look_around.py`
  - `brain/cognition/perception/look_outward.py`
  - `brain/cognition/planning/env_snapshot.py`
  - `brain/cognition/planning/evolution.py`
  - `brain/cognition/planning/goal_lifecycle.py`
  - `brain/cognition/planning/goals.py`
  - `brain/cognition/planning/introspection.py`
  - `brain/cognition/planning/motivations.py`
  - `brain/cognition/planning/pursue_goal.py`
  - `brain/cognition/planning/reflection.py`
  - `brain/cognition/planning/thinking_depth.py`
  - `brain/cognition/prediction.py`
  - `brain/cognition/privacy.py`
  - `brain/cognition/reflection/meta_reflect.py`
  - `brain/cognition/reflection/reflect_on_cognition.py`
  - `brain/cognition/reflection/reflect_on_cognition_schedule.py`
  - `brain/cognition/reflection/reflect_on_conversation.py`
  - `brain/cognition/reflection/reflect_on_internal_agents.py`
  - `brain/cognition/reflection/reflect_on_outcome.py`
  - `brain/cognition/reflection/reflect_on_self_belief.py`
  - `brain/cognition/reflection/rule_reflection.py`
  - `brain/cognition/reflection/self_reflection.py`
  - `brain/cognition/reflection_metadata.py`
  - `brain/cognition/regret.py`
  - `brain/cognition/repair/auto_repair.py`
  - `brain/cognition/repair/repair.py`
  - `brain/cognition/reward_calibrator.py`
  - `brain/cognition/rss_reader.py`
  - `brain/cognition/rumination.py`
  - `brain/cognition/search_own_files.py`
  - `brain/cognition/seek_novelty.py`
  - `brain/cognition/self_extension.py`
  - `brain/cognition/self_generated/autogenerated_thoughts.py`
  - `brain/cognition/selfhood/autobiography.py`
  - `brain/cognition/selfhood/boundary_check.py`
  - `brain/cognition/selfhood/ethics.py`
  - `brain/cognition/selfhood/fragmentation.py`
  - `brain/cognition/selfhood/identity.py`
  - `brain/cognition/selfhood/latent_identity.py`
  - `brain/cognition/selfhood/person_detector.py`
  - `brain/cognition/selfhood/relationships.py`
  - `brain/cognition/selfhood/self_model_conflicts.py`
  - `brain/cognition/selfhood/tensions.py`
  - `brain/cognition/selfhood/value_evolution.py`
  - `brain/cognition/selfhood/values_check.py`
  - `brain/cognition/skill_synthesis.py`
  - `brain/cognition/temporal_pressure.py`
  - `brain/cognition/temporal_state.py`
  - `brain/cognition/terminal.py`
  - `brain/cognition/theory_of_mind.py`
  - `brain/cognition/threads.py`
  - `brain/cognition/tools/ask_llm.py`
  - `brain/cognition/web_research.py`
  - `brain/cognition/wikipedia_search.py`
  - `brain/cognition/wonder.py`
  - `brain/cognition/world_model.py`
  - `brain/core/config/settings.py`
  - `brain/core/drive.py`
  - `brain/core/manager.py`
  - `brain/embodiment/subconscious.py`
  - `brain/embodiment/system_presence.py`
  - `brain/embodiment/world_model.py`
  - `brain/eval/evaluator_daemon.py`
  - `brain/eval/evaluator_wal.py`
  - `brain/goals_bridge.py`
  - `brain/motivation/energy_orientation.py`
  - `brain/peers/peer_base.py`
  - `brain/peers/peer_registry.py`
  - `brain/registry/behavior_registry.py`
  - `brain/registry/cognition_registry.py`
  - `brain/symbolic/analogy_engine.py`
  - `brain/symbolic/autonomous_experiment.py`
  - `brain/symbolic/benchmark.py`
  - `brain/symbolic/causal_graph.py`
  - `brain/symbolic/concept_formation.py`
  - `brain/symbolic/crystallization.py`
  - `brain/symbolic/embodied_actions.py`
  - `brain/symbolic/ground_truth.py`
  - `brain/symbolic/intrinsic_motivation.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/symbolic/meta_rules.py`
  - `brain/symbolic/pattern_scorer.py`
  - `brain/symbolic/prediction_engine.py`
  - `brain/symbolic/progress_tracker.py`
  - `brain/symbolic/reasoning_router.py`
  - `brain/symbolic/rule_abstraction.py`
  - `brain/symbolic/rule_compressor.py`
  - `brain/symbolic/rule_engine.py`
  - `brain/symbolic/rule_forgetting.py`
  - `brain/symbolic/rule_synthesis.py`
  - `brain/symbolic/rule_verifier.py`
  - `brain/symbolic/self_improvement.py`
  - `brain/symbolic/symbolic_cognition.py`
  - `brain/symbolic/symbolic_dictionary.py`
  - `brain/symbolic/symbolic_dream.py`
  - `brain/symbolic/symbolic_fluency.py`
  - `brain/symbolic/symbolic_reflection.py`
  - `brain/symbolic/symbolic_search.py`
  - `brain/symbolic/symbolic_self_model.py`
  - `brain/symbolic/temporal_planner.py`
  - `brain/think/attention_weights.py`
  - `brain/think/depth_bandit.py`
  - `brain/think/inner_loop.py`
  - `brain/think/loop_helpers.py`
  - `brain/think/meta_controller.py`
  - `brain/think/safe_runner.py`
  - `brain/think/simulate.py`
  - `brain/think/speech_evaluator.py`
  - `brain/think/speech_generator.py`
  - `brain/think/speech_log.py`
  - `brain/think/state_processor.py`
  - `brain/think/thalamus.py`
  - `brain/think/think_generate.py`
  - `brain/think/think_module.py`
  - `brain/think/think_utils/action_gate.py`
  - `brain/think/think_utils/execute_cognitive_actions.py`
  - `brain/think/think_utils/finalize.py`
  - `brain/think/think_utils/select_function.py`
  - `brain/think/think_utils/talk_policy.py`
  - `brain/think/think_utils/user_input.py`
  - `brain/utils/append.py`
  - `brain/utils/core_utils.py`
  - `brain/utils/emotion_utils.py`
  - `brain/utils/error.py`
  - `brain/utils/error_router.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/hash_utils.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/load_utils.py`
  - `brain/utils/log_reflection.py`
  - `brain/utils/memory_utils.py`
  - `brain/utils/response_utils.py`
  - `brain/utils/state_guard.py`
  - `brain/utils/timing.py`

## `brain/utils/log_reflection.py`
**Imports:**
  - `brain/utils/append.py`
  - `brain/utils/log.py`
  - `brain/utils/paths.py`
**Imported by:** (13 files)
  - `brain/affect/reflect_on_affect.py`
  - `brain/affect/reflect_on_affect_model.py`
  - `brain/cognition/maintenance/self_review.py`
  - `brain/cognition/planning/introspection.py`
  - `brain/cognition/reflection/reflect_on_cognition.py`
  - `brain/cognition/reflection/reflect_on_cognition_schedule.py`
  - `brain/cognition/reflection/reflect_on_conversation.py`
  - `brain/cognition/reflection/reflect_on_internal_agents.py`
  - `brain/cognition/reflection/reflect_on_outcome.py`
  - `brain/cognition/reflection/reflect_on_self_belief.py`
  - `brain/cognition/reflection/rule_reflection.py`
  - `brain/cognition/reflection/self_reflection.py`
  - `brain/cognition/repair/repair.py`

## `brain/utils/manage_cycle_count.py`
**Imports:**
  - `brain/utils/json_utils.py`
  - `brain/utils/paths.py`
**Imported by:** (1 files)
  - `brain/think/think_module.py`

## `brain/utils/manifest.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/utils/memory_graph.py`
**Imports:**
  - `brain/utils/json_utils.py`
  - `brain/utils/paths.py`
**Imported by:** (1 files)
  - `brain/cog_memory/long_memory.py`

## `brain/utils/memory_health.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/utils/memory_utils.py`
**Imports:**
  - `brain/utils/log.py`
**Imported by:** (2 files)
  - `brain/cog_memory/long_memory.py`
  - `brain/cog_memory/summarize_w_memory.py`

## `brain/utils/metrics_sampling.py`
**Imports:**
  - `brain/utils/sys_events.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/utils/num.py`
**Imports:** *(none within project)*
**Imported by:** (1 files)
  - `brain/cognition/reflection/reflect_on_cognition.py`

## `brain/utils/path_redact.py`
**Imports:** *(none within project)*
**Imported by:** (3 files)
  - `brain/utils/error.py`
  - `brain/utils/error_router.py`
  - `brain/utils/log.py`

## `brain/utils/paths.py`
**Imports:** *(none within project)*
**Imported by:** (27 files)
  - `brain/utils/bandit.py`
  - `brain/utils/checkpoint.py`
  - `brain/utils/core_utils.py`
  - `brain/utils/emotion_utils.py`
  - `brain/utils/emotional_feedback.py`
  - `brain/utils/error.py`
  - `brain/utils/error_router.py`
  - `brain/utils/events.py`
  - `brain/utils/events_miner.py`
  - `brain/utils/failure_counter.py`
  - `brain/utils/feedback_log.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/get_cycle_count.py`
  - `brain/utils/knowledge_utils.py`
  - `brain/utils/load_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/log_reflection.py`
  - `brain/utils/manage_cycle_count.py`
  - `brain/utils/memory_graph.py`
  - `brain/utils/response_utils.py`
  - `brain/utils/self_model.py`
  - `brain/utils/state.py`
  - `brain/utils/state_guard.py`
  - `brain/utils/summarizers.py`
  - `brain/utils/timing.py`
  - `brain/utils/token_meter.py`
  - `brain/utils/trace_buffer.py`

## `brain/utils/response_utils.py`
**Imports:**
  - `brain/cognition/selfhood/identity.py`
  - `brain/utils/coerce_to_string.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/paths.py`
  - `brain/utils/self_model.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/utils/runtime_ctx.py`
**Imports:** *(none within project)*
**Imported by:** (3 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/selfhood/identity.py`
  - `brain/think/think_module.py`

## `brain/utils/self_model.py`
**Imports:**
  - `brain/utils/json_utils.py`
  - `brain/utils/paths.py`
**Imported by:** (30 files)
  - `brain/ORRIN_loop.py`
  - `brain/affect/discovery.py`
  - `brain/behavior/revise.py`
  - `brain/cognition/dreaming/dream_cycle.py`
  - `brain/cognition/innovation/bootstrap.py`
  - `brain/cognition/innovation/evaluation.py`
  - `brain/cognition/innovation/innovation.py`
  - `brain/cognition/maintenance/self_modeling.py`
  - `brain/cognition/planning/evolution.py`
  - `brain/cognition/planning/introspection.py`
  - `brain/cognition/planning/motivations.py`
  - `brain/cognition/reflection/meta_reflect.py`
  - `brain/cognition/reflection/reflect_on_internal_agents.py`
  - `brain/cognition/reflection/reflect_on_outcome.py`
  - `brain/cognition/reflection/reflect_on_self_belief.py`
  - `brain/cognition/sandbox.py`
  - `brain/cognition/selfhood/autobiography.py`
  - `brain/cognition/selfhood/ethics.py`
  - `brain/cognition/selfhood/fragmentation.py`
  - `brain/cognition/selfhood/identity.py`
  - `brain/cognition/selfhood/self_model_conflicts.py`
  - `brain/cognition/selfhood/value_evolution.py`
  - `brain/cognition/selfhood/values_check.py`
  - `brain/cognition/terminal.py`
  - `brain/cognition/world_model.py`
  - `brain/think/think_utils/execute_cognitive_actions.py`
  - `brain/think/think_utils/user_input.py`
  - `brain/utils/emotion_utils.py`
  - `brain/utils/generate_response.py`
  - `brain/utils/response_utils.py`

## `brain/utils/servers.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/utils/signal_utils.py`
**Imports:** *(none within project)*
**Imported by:** (17 files)
  - `brain/ORRIN_loop.py`
  - `brain/affect/stagnation_signal_escalation.py`
  - `brain/affect/reward_signals/reward_signals.py`
  - `brain/cognition/awaiting_response.py`
  - `brain/cognition/innovation/bootstrap.py`
  - `brain/cognition/innovation/evaluation.py`
  - `brain/cognition/local_search_signal.py`
  - `brain/cognition/perception/fs_perception.py`
  - `brain/cognition/planning/goals.py`
  - `brain/cognition/prediction.py`
  - `brain/cognition/selfhood/values_check.py`
  - `brain/cognition/threads.py`
  - `brain/cognition/wonder.py`
  - `brain/peers/peer_base.py`
  - `brain/think/thalamus.py`
  - `brain/think/think_utils/action_gate.py`
  - `brain/think/think_utils/user_input.py`

## `brain/utils/state.py`
**Imports:**
  - `brain/utils/json_utils.py`
  - `brain/utils/paths.py`
**Imported by:** *(not imported by any tracked file)*

## `brain/utils/state_guard.py`
**Imports:**
  - `brain/utils/json_utils.py`
  - `brain/utils/log.py`
  - `brain/utils/paths.py`
**Imported by:** (2 files)
  - `brain/ORRIN_loop.py`
  - `brain/cognition/repair/auto_repair.py`

## `brain/utils/summarizers.py`
**Imports:**
  - `brain/utils/json_utils.py`
  - `brain/utils/paths.py`
**Imported by:** (4 files)
  - `brain/behavior/revise.py`
  - `brain/cognition/innovation/bootstrap.py`
  - `brain/cognition/innovation/innovation.py`
  - `brain/cognition/planning/evolution.py`

## `brain/utils/sys_events.py`
**Imports:** *(none within project)*
**Imported by:** (2 files)
  - `brain/utils/alive_brain.py`
  - `brain/utils/metrics_sampling.py`

## `brain/utils/tamper_guard.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/utils/timing.py`
**Imports:**
  - `brain/utils/log.py`
  - `brain/utils/paths.py`
**Imported by:** (5 files)
  - `brain/affect/update_affect_state.py`
  - `brain/cognition/selfhood/ethics.py`
  - `brain/cognition/selfhood/identity.py`
  - `brain/think/think_utils/finalize.py`
  - `brain/think/think_utils/user_input.py`

## `brain/utils/token_meter.py`
**Imports:**
  - `brain/utils/paths.py`
**Imported by:** (4 files)
  - `brain/ORRIN_loop.py`
  - `brain/symbolic/llm_gate.py`
  - `brain/think/simulate.py`
  - `brain/utils/generate_response.py`

## `brain/utils/trace_buffer.py`
**Imports:**
  - `brain/utils/paths.py`
**Imported by:** (2 files)
  - `brain/cognition/finetuning/finetune_pipeline.py`
  - `brain/think/think_utils/finalize.py`

## `brain/utils/ui_build.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*

## `brain/utils/validators.py`
**Imports:** *(none within project)*
**Imported by:** *(not imported by any tracked file)*
