---
name: reteno-email-editor
description: Read Reteno email export manifests and clone or update them through Reteno MCP while preserving Reteno's original verbose builder HTML. Use for MCP-backed Reteno email text editing in this repo.
version: 0.1.1
---

# Reteno Email Editor

## Overview

Use explicit `read`, `clone`, and `update` modes:
- `read`: call `get_email_message_export(message_id)`, download the exported files from the returned manifest, and write local files only.
- `clone`: create a new Reteno email message by uploading the local HTML and CSS into a short-lived upload session, then finalizing the message.
- `update`: update an existing Reteno email message by uploading the local HTML and CSS into a short-lived upload session, then finalizing the update.

This skill is for narrowly scoped copy edits inside an existing Reteno template. Keep the original verbose Reteno builder HTML. Do not rewrite the email as a new simplified document.

## Workflow

1. `read`: call the MCP tool `get_email_message_export(message_id=<ID>)` to fetch the source message export manifest by ID.
2. Use the manifest download links to retrieve the source files without pulling the full email body into the MCP tool response.
3. Write local files to `output/reteno`:
   - `email_<ID>.json`: full normalized email JSON from the export.
   - `email_<ID>.html`: the editable HTML from the export, when present. This is the file to edit.
   - `email_<ID>.css`: the dedicated Reteno `css` field from the export, when present.
4. Edit `output/reteno/email_<ID>.html` in place.
   - Change only visible text inside elements whose class contains `esd-block-text` or `esd-block-button`.
   - You may also change message-level `subject` and `preheader` values outside the HTML when the task requires it.
   - Do not change any other HTML text, attributes, classes, IDs, language tags, links, image URLs, alt text, comments, tracking markup, or block metadata.
   - Do not replace the file with a newly authored HTML document.
   - Do not remove Reteno wrappers, table structure, tracking markup, inline styles, conditional comments, or other verbose builder output.
5. `clone` or `update`: read the edited `html` file, prepare a Reteno upload session, upload `html` and the original source `css` to the returned HTTP endpoints, then finalize through Reteno MCP.
   - Always upload the original source message `css` field as the session's `css` artifact unless the user explicitly provides replacement CSS.
   - Never send empty CSS unless the source message CSS is actually empty.
   - Never extract, infer, rebuild, or synthesize CSS from the HTML document, `<head>`, or `<style>` tags.

## Mode Details

### `read`

Call `get_email_message_export(message_id=<SOURCE_ID>)`, download the exported artifacts from the manifest links, then write the local files listed above.

Edit this file:

- `output/reteno/email_<SOURCE_ID>.html`

Treat that file as the source of truth. Preserve its overall structure and edit only text nodes inside existing `esd-block-text` and `esd-block-button` blocks.

Do not treat `email_<SOURCE_ID>.html` as the CSS source. CSS comes from the separate Reteno `css` field only.
Do not expect Reteno storage field names in the exported JSON. Current `reteno-mcp` exposes the editable document as `html`.

### `clone`

Use the fetched source message as defaults, load the edited local `html` file, call `prepare_email_message_upload(operation="create")`, upload the edited `html` and source `css`, then create the message with Reteno MCP `create_email_message`.

Allowed changes for `clone` are limited to:
- text inside existing `esd-block-text` blocks
- text inside existing `esd-block-button` blocks
- message `subject`
- message `preheader`

Everything else must stay byte-for-byte unchanged where practical, including layout markup, links, images, classes, attributes, CSS, and Reteno config blocks.

Build the payload with these defaults unless the user explicitly overrides them:

- `name`
- `from`
- `subject`
- `languageCode`
- `tags`
- `subscriptionsKeys`
- `preheader` only if the source payload exposes it and the task requires changing it

The uploaded `css` artifact is mandatory: always copy it from the source message's dedicated `css` field. Do not omit it, clear it, replace it with empty CSS, or derive it from HTML during clone.

Send this write payload shape:

- `uploadSessionId` = returned by `prepare_email_message_upload`
- other copied metadata fields as listed above

Do not manually send `html` or `css` to `create_email_message`. Current `reteno-mcp` requires those files to be uploaded first and finalized by `uploadSessionId`.

Because this skill preserves the original verbose Reteno HTML, the uploaded message should retain the builder-style markup rather than a stripped custom document.

If the user asks for the created message link or preview, call `get_email_message_view_link` for the new message ID.

### `update`

Use the same source-default behavior as `clone`, but call `prepare_email_message_upload(operation="update", message_id=<TARGET_ID>)` and then Reteno MCP `update_email_message` for the target message ID instead of creating a new message.

Always include the original source message `css` field in the uploaded CSS artifact unless the user explicitly provides replacement CSS. Do not extract CSS from the HTML document.
Send `uploadSessionId`, not `html` or `css`, to `update_email_message`.

Allowed changes for `update` are the same as `clone`: edit only text in existing `esd-block-text` and `esd-block-button` blocks, plus `subject` and `preheader` if requested.

`update` needs two IDs:
- source ID: the message you read and use as the default field source
- target ID: the existing message to overwrite with the edited local HTML

## Defaults and Notes

- Use Reteno MCP tools, not direct API calls or local HTTP scripts.
- Use the MCP tool `get_email_message_export(message_id)` for reads.
- Keep the local editing flow centered on `output/reteno/email_<SOURCE_ID>.html`.
- Persist the original Reteno verbose HTML structure. Never simplify, re-template, prettify, or regenerate the document from scratch.
- This editor may change only text inside existing `esd-block-text` and `esd-block-button` blocks, plus `subject` and `preheader` when requested.
- Do not add blocks, remove blocks, move blocks, rename classes, alter links, alter image sources, alter alt text, alter `lang`, alter head contents, alter inline styles, or alter config/tracking sections.
- Unless the user requests overrides, copy source values for `name`, `from`, `subject`, `languageCode`, `tags`, and `subscriptionsKeys`.
- Always persist the original message `css` when cloning or updating. Missing CSS can make the uploaded email appear stripped even if the HTML structure is preserved.
- Read CSS from the dedicated Reteno `css` field when fetching the message, persist that same field on writes, and never reconstruct CSS from the HTML.
- Current `reteno-mcp` exports expose the editable document as `html`.
- Current `reteno-mcp` writes require an upload session. Upload `html` and `css` first, then finalize with `uploadSessionId`.
- `get_email_message_export` returns a manifest with signed download URLs for `json`, `html`, and `css` artifacts, plus per-translation artifacts when present.
- Do not inject duplicate CSS into the HTML document, and do not remove trailing Reteno blocks such as `esd-config-block`.
- This skill supports reading, cloning, updating, and optionally retrieving a view link.
- This revision does not support image uploads to Reteno content storage.
- Do not use JWT/content upload endpoints or filename-based image URL rewriting in this skill.
- If an uploaded message looks stripped, that means the local `email_<ID>.html` file was replaced with simplified markup before clone/update. Reteno stored exactly what was sent.

## Resources

No bundled scripts are required for the primary workflow in this revision. Perform Reteno operations through MCP tools and use normal local file editing for HTML changes.
