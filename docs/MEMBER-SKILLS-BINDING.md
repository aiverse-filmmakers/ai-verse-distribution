# Composed member Skills binding

Step 4 local implementation; exact refs and cross-platform release admission are
step 5. Do not update a member installation directly from these checkouts.

During matching Skills setup/reconcile, Distribution obtains the actual root from
owner status, previews OS `capability-configuration-cli.mjs`, establishes the
Skills `library configure-learning` destination, then applies the OS binding with
its expected metadata digest. Both owners remain authoritative. A partial failure
can be retried with the same roots; conflicts refuse without moving member files.

Fresh setup uses `<managed-root-parent>/member-skills`. An existing OS setup with
no new binding retains its prior canonical personal root, including its established
explicit environment override. Existing bindings are preserved; only an exact
owner entrypoint refresh can accompany a source update. Binding writes never move
old skills or grant workspace/connection permissions. Old owners without the new
OS API follow their existing lifecycle; mismatched new OS/old Skills refuses.

Recovery and preservation obtain personal roots through the OS owner, preserving
member content and explicit external registrations. Root drift is a preservation
failure. Optional adapter discovery obtains the current same root/entrypoint,
while native trust and callback evidence remain separate qualification gates.

Validation uses the OS `test-shared-skills-runtime.py` disposable owner-composition
fixture plus existing adapter, preservation and recovery regressions. No actual
Core install/update or release pin changes are part of step 4.
