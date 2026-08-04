"""Shared test fixtures: keypoint names, pose builders and hand-written fakes.

Import from the submodules explicitly -- `from tests._support.builders import
make_person` -- rather than re-exporting here, so that a reader of any test can
see which file a name came from.

Nothing in this package may import `worksite_detector`: these fixtures have to
be constructible before the module under test exists, and a fixture that leans
on production code cannot prove that production code wrong.
"""
