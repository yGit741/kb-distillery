"""`ship protect`: the repo's merge settings as the user and, with --ruleset, the branch ruleset on main (create or update)."""
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from kb_distillery.git import ship

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _cp(stdout="", rc=0):
    return SimpleNamespace(returncode=rc, stdout=stdout, stderr="")


class ProtectTest(unittest.TestCase):
    def _run(self, rulesets, ruleset=True, queue_refused=False):
        calls, bodies = [], []

        def fake_gh(args, root=None, user=False):
            calls.append((list(args), user))
            if args[:2] == ["api", "repos/{owner}/{repo}/rulesets"]:
                return _cp(json.dumps(rulesets))
            if "--input" in args:
                with open(args[args.index("--input") + 1]) as f:
                    bodies.append(json.load(f))
                if queue_refused and any(r["type"] == "merge_queue" for r in bodies[-1]["rules"]):
                    return SimpleNamespace(returncode=1, stdout="", stderr="gh: Validation Failed (HTTP 422)")
            return _cp()

        with patch.object(ship, "gh", fake_gh), patch("builtins.print"):
            rc = ship.cmd_protect(root="/tmp", ruleset=ruleset)
        return rc, [a for a, _ in calls], [u for _, u in calls], bodies

    def test_merge_settings_as_the_user_and_no_ruleset_without_the_flag(self):
        rc, args, users, bodies = self._run([], ruleset=False)
        self.assertEqual(rc, 0)
        self.assertTrue(all(users), "repo settings need the user's token: the App has no administration permission")
        self.assertIn("--enable-squash-merge=false", args[0])
        self.assertIn("--enable-auto-merge=true", args[0])             # `ship merge` arms auto-merge; off, gh merges directly instead
        self.assertIn("merge_commit_title=PR_TITLE", args[1])          # the queue writes the merge commit: `<title> (#N)`
        self.assertIn("merge_commit_message=PR_BODY", args[1])         # with the PR body (KB-Version and the commit list)
        self.assertEqual(len(args), 2)
        self.assertEqual(bodies, [])

    def test_ruleset_created_when_main_has_none(self):
        rc, args, _, bodies = self._run([])
        self.assertEqual(rc, 0)
        post = next(a for a in args if "POST" in a)
        self.assertEqual(post[3], "repos/{owner}/{repo}/rulesets")
        self.assertEqual(bodies, [ship.ruleset_body()])

    def test_ruleset_updated_in_place_when_present(self):
        rc, args, _, bodies = self._run([{"id": 42, "name": "main"}, {"id": 7, "name": "other"}])
        self.assertEqual(rc, 0)
        put = next(a for a in args if "PUT" in a)
        self.assertEqual(put[3], "repos/{owner}/{repo}/rulesets/42")
        self.assertFalse(any("POST" in a for a in args))
        self.assertEqual(len(bodies), 1)

    def test_a_user_owned_repository_gets_the_ruleset_without_the_merge_queue(self):
        """GitHub refuses the merge-queue rule outside organizations (422): the same ruleset lands without it."""
        rc, args, _, bodies = self._run([], queue_refused=True)
        self.assertEqual(rc, 0)
        self.assertEqual(len(bodies), 2)
        self.assertTrue(any(r["type"] == "merge_queue" for r in bodies[0]["rules"]))
        self.assertFalse(any(r["type"] == "merge_queue" for r in bodies[1]["rules"]))
        self.assertEqual([r["type"] for r in bodies[1]["rules"]],
                         [r["type"] for r in bodies[0]["rules"] if r["type"] != "merge_queue"])      # nothing else dropped
        self.assertEqual(sum("POST" in a for a in args), 2)
        self.assertFalse(any("--silent" in a for a in args if "--input" in a))      # GitHub's reason for a refused ruleset must reach the user

    def test_ruleset_requires_all_green_and_merges_through_the_queue(self):
        body = ship.ruleset_body()
        rules = {r["type"]: r.get("parameters", {}) for r in body["rules"]}
        self.assertTrue({"pull_request", "required_status_checks", "merge_queue", "non_fast_forward", "deletion"} <= set(rules))
        self.assertEqual([c["context"] for c in rules["required_status_checks"]["required_status_checks"]], [ship.REQUIRED_CHECK])
        self.assertEqual(rules["pull_request"]["allowed_merge_methods"], ["merge"])
        self.assertEqual(rules["merge_queue"]["merge_method"], "MERGE")
        # the owner's hotfix route: the admin role may bypass, through a pull request only, never by pushing main
        self.assertEqual(body["bypass_actors"], [{"actor_id": ship.ADMIN_ROLE, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"}])
        self.assertEqual(body["conditions"]["ref_name"]["include"], ["~DEFAULT_BRANCH"])

    def test_the_required_check_is_a_job_in_ci_yml(self):
        with open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8") as f:
            wf = yaml.safe_load(f)
        self.assertIn(ship.REQUIRED_CHECK, wf["jobs"])


if __name__ == "__main__":
    unittest.main()
