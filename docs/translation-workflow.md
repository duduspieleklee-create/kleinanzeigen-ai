# Translation Workflow Documentation

## Overview

The `.github/workflows/github_translate.yaml` workflow is a **repository maintenance tool** that automatically translates the README.md file into multiple languages when changes are pushed to the repository.

## Important: Scope Clarification

**This is NOT an application feature.** The translation workflow:

- ✅ **IS**: A GitHub Actions workflow that translates README.md for international contributors
- ✅ **IS**: Repository documentation tooling only
- ❌ **IS NOT**: Part of the kleinanzeigen-ai application functionality
- ❌ **IS NOT**: Used for translating user-facing content in the app
- ❌ **IS NOT**: A product feature that end-users interact with

## How It Works

The workflow uses the `Lin-jun-xiang/action-translate-readme@v2` GitHub Action to:

1. Detect changes to README.md on any branch push
2. Automatically translate the README into configured languages (English, Chinese Traditional, Chinese Simplified, French, Arabic)
3. Commit the translated versions back to the repository

## Configuration

The workflow requires optional API keys for translation services:

- `AUTO_TRANSLATE`: GitHub token for committing translations
- `zhipuai_api_key`: Optional ZhipuAI API key
- `openai_api_key`: Optional OpenAI API key

These secrets are configured in the GitHub repository settings and are **only used by the GitHub Actions workflow**, not by the application code.

## Target Languages

Currently configured to translate README.md into:
- English (en)
- Traditional Chinese (zh-TW)
- Simplified Chinese (zh-CN)
- French (French)
- Arabic (Arabic)

## For Developers

If you're looking to add translation/internationalization features to the **application itself**, this workflow is not relevant. You would need to:

1. Implement i18n in the FastAPI application (e.g., using `babel` or similar)
2. Add translation files for the web UI templates
3. Configure language detection and switching in the application

The translation workflow documented here is purely for maintaining multilingual README documentation in the repository.
