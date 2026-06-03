"""Internal prompt templates for AI-backed services.

Underscore prefix marks the package as service-private — only files under
`app/services/` should import from here. Keep raw prompt strings in this
package so they never leak through schemas, logs, or HTTP responses.
"""
