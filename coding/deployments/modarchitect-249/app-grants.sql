GRANT USAGE ON SCHEMA public TO modarchitect_app;
GRANT SELECT ON resource_scopes, model_component_definitions, research_designs,
    research_design_drafts, research_design_versions, research_design_components TO modarchitect_app;
GRANT INSERT ON resource_scopes, research_designs, research_design_drafts,
    research_design_versions, research_design_components TO modarchitect_app;
GRANT UPDATE (revision, configuration_json, configuration_sha256, updated_at)
    ON research_design_drafts TO modarchitect_app;
GRANT SELECT, INSERT ON research_design_saves TO modarchitect_app;

GRANT SELECT, INSERT ON research_runs, research_trained_models,
    research_design_data, research_dispatch_queue TO modarchitect_app;
GRANT UPDATE (status, attempt_id, lease_until, scheduler_id, result_json,
    result_sha256, error, updated_at) ON research_runs TO modarchitect_app;
GRANT UPDATE (status, claimed_at) ON research_dispatch_queue TO modarchitect_app;
GRANT UPDATE (observations_json, observations_sha256, data_kind, draft_revision)
    ON research_design_data TO modarchitect_app;
GRANT UPDATE (source_snapshot_ids) ON research_design_data TO modarchitect_app;

GRANT SELECT, INSERT ON input_acquisitions, input_source_snapshots,
    input_acquisition_dispatch TO modarchitect_app;
GRANT UPDATE (status, attempt_id, lease_until, scheduler_id, result_sha256,
    error, updated_at) ON input_acquisitions TO modarchitect_app;
GRANT UPDATE (status, claimed_at) ON input_acquisition_dispatch TO modarchitect_app;

GRANT SELECT, INSERT ON research_dataset_snapshots, research_report_tasks,
    research_report_batches, research_report_task_index, research_report_work TO modarchitect_app;
GRANT UPDATE (status, revision, updated_at) ON research_report_tasks TO modarchitect_app;
GRANT UPDATE (active, next_observation_day) ON research_report_task_index TO modarchitect_app;
GRANT UPDATE (status, acquisition_ids, dataset_id, run_id, manual_json, attempts_json,
    lease_token, lease_until, error, updated_at) ON research_report_batches TO modarchitect_app;
GRANT UPDATE (status, next_check_at) ON research_report_work TO modarchitect_app;
