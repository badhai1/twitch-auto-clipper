from pathlib import Path
import json
import unittest


class WorkflowTests(unittest.TestCase):
    def test_clipper_schedule_is_active_and_gated_by_repository_variable(self):
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "clipper.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('\n  schedule:\n    - cron: "3-58/5 * * * *"', workflow)
        self.assertNotIn("# schedule:", workflow)
        self.assertIn("vars.TWITCH_CLIPPER_ENABLED == 'true'", workflow)
        self.assertIn("group: twitch-auto-clipper", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("default: true", workflow)

    def test_test_workflow_does_not_require_twitch_secrets(self):
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "tests.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("python -m unittest discover", workflow)
        self.assertNotIn("TWITCH_REFRESH_TOKEN", workflow)
        self.assertNotIn("TOKEN_ENCRYPTION_KEY", workflow)

    def test_external_dispatcher_defaults_to_a_safe_probe_every_five_minutes(self):
        config = json.loads(
            (Path(__file__).parents[1] / "cloudflare" / "wrangler.jsonc").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(config["triggers"]["crons"], ["3-58/5 * * * *"])
        self.assertFalse(config["workers_dev"])
        dispatcher = (
            Path(__file__).parents[1] / "cloudflare" / "dispatcher.mjs"
        ).read_text(encoding="utf-8")
        self.assertIn('env.TARGET_MODE || "probe"', dispatcher)
        self.assertIn('dry_run: "false"', dispatcher)

    def test_probe_workflow_never_uses_twitch_secrets(self):
        workflow = (
            Path(__file__).parents[1]
            / ".github"
            / "workflows"
            / "dispatch-probe.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch", workflow)
        self.assertIn("permissions: {}", workflow)
        self.assertIn("group: twitch-auto-clipper-dispatch-probe", workflow)
        self.assertNotIn("TWITCH_CLIENT_ID", workflow)
        self.assertNotIn("TWITCH_REFRESH_TOKEN", workflow)
        self.assertNotIn("TOKEN_ENCRYPTION_KEY", workflow)


if __name__ == "__main__":
    unittest.main()
