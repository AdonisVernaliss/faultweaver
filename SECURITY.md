# Security policy

Faultweaver is security testing software intended only for explicitly authorized targets.

Please do not disclose suspected vulnerabilities in public issues. Until a private disclosure channel is published, retain the report and contact the maintainers through the repository owner's private contact methods.

Faultweaver redacts common secret-bearing headers and structured body fields in API responses, validation errors, logs, and workspace views by default. Local project databases intentionally retain identity credentials and replay material and must be protected accordingly.
