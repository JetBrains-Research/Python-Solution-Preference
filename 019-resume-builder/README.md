# Resume Builder API

A simple HTTP API for managing a single resume.

## Endpoints

### Public Read

- `GET /resume` - Get the full resume (returns error if not set up yet)
- `GET /resume/experience` - Get experience entries
- `GET /resume/education` - Get education entries
- `GET /resume/skills` - Get skills list

### Edit Operations (require password)

All edit operations require the header `X-Resume-Password: resume-editor-2025`

- `POST /resume` - Save/update the full resume
- `POST /resume/experience` - Add an experience entry
- `PUT /resume/experience/<index>` - Update an experience entry
- `DELETE /resume/experience/<index>` - Delete an experience entry
- `POST /resume/education` - Add an education entry
- `PUT /resume/education/<index>` - Update an education entry
- `DELETE /resume/education/<index>` - Delete an education entry
- `POST /resume/skills` - Add a skill
- `DELETE /resume/skills/<index>` - Delete a skill

## Field Validation

- Headline: Required, max 100 characters
- Summary: Optional, max 500 characters
- Experience: Title (required, max 100), Date range (required, max 100), Description (required, max 1000)
- Education: School name (required, max 100), Program (required, max 100), Date range (required, max 100)
- Skills: Max 50 characters each, no duplicates (case-insensitive)

## Running the Server
