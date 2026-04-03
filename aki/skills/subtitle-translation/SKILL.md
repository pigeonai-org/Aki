---
name: subtitle-translation
description: Translates the audio/video into localized subtitle files using specialized agent delegates.
---

# Subtitle Translation Playbook

When given a request to translate a video or audio file into another language, follow these exact phases in order.

## Phase 0: Agent Setup
1. Call `read_skill` with `skill_name="agent-creation"` before delegation.
2. Use that skill as the role contract for `Orchestrator`, `MediaExtractor`, `Localizer`, and `QAEditor`.

## Phase 1: Preparation
1. Identify the source media file (audio or video path) from the user's prompt.
2. Identify the target language from the user's prompt.
3. Validate that you have the required inputs.

## Phase 2: Media Extraction (Delegate)
1. Use the `delegate_to_worker` tool to assign tasks to the `MediaExtractor`.
2. Pass the media path and instruct the worker to:
   - Extract audio if it is a video file.
   - Run Voice Activity Detection (VAD) to segment the audio.
   - Wait for VAD success and chunk metadata before starting transcription.
   - Transcribe each VAD segment sequentially (never in parallel) using the chunk order.
   - Use ISO-639-1 language values (e.g., `zh`, `en`) when passing `language`.
3. Wait for the `MediaExtractor` to return the English (or source language) transcription.

## Phase 3: Localization (Delegate)
1. Use the `delegate_to_worker` tool to assign tasks to the `Localizer`.
2. Pass the transcription received from Phase 2 and the target language.
3. Instruct the `Localizer` to:
   - Translate the subtitle segments into the target language.
   - Perform any necessary subtitle editing to maintain flow.
4. Wait for the `Localizer` to return the translated subtitles.

## Phase 4: Quality Assurance and Output (Delegate)
1. Use the `delegate_to_worker` tool to assign a task to the `QAEditor`.
2. Pass the translated subtitles.
3. Instruct the `QAEditor` to:
   - Proofread the translated text.
   - Write the final result into an `.srt` format file.
4. Wait for the `.srt` output.

## Phase 5: Completion
1. Review the generated `.srt` file.
2. Formulate a final response back to the user indicating the translation is complete and provide the path to the SRT file.
3. Mark the task as Complete.
