/**
 * toolDefinitions.ts — Tool schemas for agentic AI operations.
 *
 * Two types of tools:
 * 1. FILE_TOOLS: Local file system access via Tauri (read, write, execute)
 * 2. API_TOOLS: Backend API operations (Pass, Drive, Mail, Calendar)
 *
 * These are passed to the AI as available tools. The AI decides when to call them.
 */

export interface ToolDefinition {
  name: string
  description: string
  input_schema: {
    type: 'object'
    properties: Record<string, { type: string; description: string; enum?: string[]; items?: any }>
    required: string[]
  }
}

// ─── Local File System Tools (Tauri) ───────────────────────────────────────

export const FILE_TOOLS: ToolDefinition[] = [
  {
    name: 'read_file',
    description:
      'Read the full contents of a file on the local file system. ' +
      'Use this to inspect source code, config files, documents, or any text file.',
    input_schema: {
      type: 'object',
      properties: {
        path: {
          type: 'string',
          description: 'Absolute or relative path to the file to read.',
        },
      },
      required: ['path'],
    },
  },
  {
    name: 'write_file',
    description:
      'Write or overwrite a file on the local file system. ' +
      'Use this to create new files, save changes, or update configs.',
    input_schema: {
      type: 'object',
      properties: {
        path: {
          type: 'string',
          description: 'Absolute or relative path to write.',
        },
        content: {
          type: 'string',
          description: 'The full text content to write to the file.',
        },
      },
      required: ['path', 'content'],
    },
  },
  {
    name: 'list_directory',
    description:
      'List files and subdirectories in a directory. ' +
      'Use this to explore the structure of a project or folder.',
    input_schema: {
      type: 'object',
      properties: {
        path: {
          type: 'string',
          description: 'Absolute or relative path to the directory to list.',
        },
      },
      required: ['path'],
    },
  },
  {
    name: 'search_files',
    description:
      'Search for a pattern in files under a directory. ' +
      'Returns matching lines with file paths. ' +
      'Equivalent to grep -r.',
    input_schema: {
      type: 'object',
      properties: {
        pattern: {
          type: 'string',
          description: 'Text pattern or regex to search for.',
        },
        directory: {
          type: 'string',
          description: 'Directory to search in (searches recursively).',
        },
        file_pattern: {
          type: 'string',
          description: 'Optional glob to filter files, e.g. "*.ts" or "*.py".',
        },
      },
      required: ['pattern', 'directory'],
    },
  },
  {
    name: 'execute_command',
    description:
      'Execute a shell command and return the output. ' +
      'Use this to run scripts, build tools, tests, git commands, or any CLI tool. ' +
      'Commands run in a bash shell. Prefer short, targeted commands.',
    input_schema: {
      type: 'object',
      properties: {
        command: {
          type: 'string',
          description: 'The shell command to execute.',
        },
        cwd: {
          type: 'string',
          description: 'Optional working directory for the command.',
        },
      },
      required: ['command'],
    },
  },
  {
    name: 'open_file_dialog',
    description:
      'Show the native OS file picker and return the selected file path. ' +
      'Use this when you need the user to select a specific file.',
    input_schema: {
      type: 'object',
      properties: {
        title: {
          type: 'string',
          description: 'Title to show in the dialog window.',
        },
        filters: {
          type: 'string',
          description: 'Optional comma-separated list of extensions to filter, e.g. "ts,js,py".',
        },
      },
      required: [],
    },
  },
  {
    name: 'open_folder_dialog',
    description:
      'Show the native OS folder picker and return the selected directory path. ' +
      'Use this when you need the user to select a project directory.',
    input_schema: {
      type: 'object',
      properties: {
        title: {
          type: 'string',
          description: 'Title to show in the dialog window.',
        },
      },
      required: [],
    },
  },
]

// ─── Backend API Tools (Pass/Drive/Mail/Calendar) ──────────────────────────

export const API_TOOLS: ToolDefinition[] = [
  {
    name: 'list_passwords',
    description: 'List all password entries in the encrypted password vault. Returns entry names, usernames, and URLs (passwords are not included in list view for security).',
    input_schema: {
      type: 'object',
      properties: {},
      required: [],
    },
  },
  {
    name: 'get_password',
    description: 'Retrieve a specific password entry including the actual password. Use this when the user asks for a specific password.',
    input_schema: {
      type: 'object',
      properties: {
        entry_id: {
          type: 'string',
          description: 'The ID of the password entry to retrieve',
        },
      },
      required: ['entry_id'],
    },
  },
  {
    name: 'create_password',
    description: 'Create a new password entry in the vault. Use this when the user wants to save a new password.',
    input_schema: {
      type: 'object',
      properties: {
        name: {
          type: 'string',
          description: 'Name/title for this password (e.g. "Gmail", "GitHub")',
        },
        username: {
          type: 'string',
          description: 'Username or email for this account',
        },
        password: {
          type: 'string',
          description: 'The password to store',
        },
        url: {
          type: 'string',
          description: 'Website URL (optional)',
        },
        notes: {
          type: 'string',
          description: 'Additional notes (optional)',
        },
      },
      required: ['name', 'password'],
    },
  },
  {
    name: 'list_notes',
    description: 'List all secure notes (credit cards, documents, custom notes) in the vault.',
    input_schema: {
      type: 'object',
      properties: {},
      required: [],
    },
  },
  {
    name: 'get_note',
    description: 'Retrieve a specific secure note with full content.',
    input_schema: {
      type: 'object',
      properties: {
        note_id: {
          type: 'string',
          description: 'The ID of the note to retrieve',
        },
      },
      required: ['note_id'],
    },
  },
  {
    name: 'create_note',
    description: 'Create a new secure note (credit card, document, or custom note).',
    input_schema: {
      type: 'object',
      properties: {
        type: {
          type: 'string',
          enum: ['credit_card', 'document', 'custom'],
          description: 'Type of note to create',
        },
        title: {
          type: 'string',
          description: 'Title for this note',
        },
        content: {
          type: 'string',
          description: 'Note content as JSON string (structure depends on type)',
        },
      },
      required: ['type', 'title', 'content'],
    },
  },
  {
    name: 'list_totp',
    description: 'List all TOTP/2FA authenticator entries in the vault.',
    input_schema: {
      type: 'object',
      properties: {},
      required: [],
    },
  },
  {
    name: 'get_totp_code',
    description: 'Generate the current TOTP code for a specific authenticator entry. The code is valid for 30 seconds.',
    input_schema: {
      type: 'object',
      properties: {
        totp_id: {
          type: 'string',
          description: 'The ID of the TOTP entry',
        },
      },
      required: ['totp_id'],
    },
  },
  {
    name: 'list_files',
    description: 'List all files in the encrypted file storage (Drive).',
    input_schema: {
      type: 'object',
      properties: {},
      required: [],
    },
  },
  {
    name: 'list_messages',
    description: 'List messages in the encrypted mailbox (inbox or sent).',
    input_schema: {
      type: 'object',
      properties: {
        folder: {
          type: 'string',
          enum: ['inbox', 'sent'],
          description: 'Which folder to list',
        },
      },
      required: ['folder'],
    },
  },
  {
    name: 'send_message',
    description: 'Send an encrypted message to another user (requires their token ID).',
    input_schema: {
      type: 'object',
      properties: {
        to_token_id: {
          type: 'string',
          description: "Recipient's Hedera token ID (e.g. '0.0.12345')",
        },
        subject: {
          type: 'string',
          description: 'Message subject',
        },
        body: {
          type: 'string',
          description: 'Message body',
        },
      },
      required: ['to_token_id', 'subject', 'body'],
    },
  },
  {
    name: 'list_events',
    description: 'List calendar events for a specific month.',
    input_schema: {
      type: 'object',
      properties: {
        year: {
          type: 'string',
          description: 'Year (e.g. "2026")',
        },
        month: {
          type: 'string',
          description: 'Month (1-12)',
        },
      },
      required: ['year', 'month'],
    },
  },
  {
    name: 'create_event',
    description: 'Create a new calendar event.',
    input_schema: {
      type: 'object',
      properties: {
        title: {
          type: 'string',
          description: 'Event title',
        },
        date: {
          type: 'string',
          description: 'Event date (YYYY-MM-DD)',
        },
        time: {
          type: 'string',
          description: 'Event time (HH:MM, optional)',
        },
        description: {
          type: 'string',
          description: 'Event description (optional)',
        },
        color: {
          type: 'string',
          description: 'Event color (optional, e.g. "blue", "red", "green")',
        },
      },
      required: ['title', 'date'],
    },
  },
]

/** Convert to Anthropic API tool format (same shape). */
export function toAnthropicTools(tools: ToolDefinition[]) {
  return tools.map((t) => ({
    name: t.name,
    description: t.description,
    input_schema: t.input_schema,
  }))
}

/** Convert to OpenAI function-calling format. */
export function toOpenAITools(tools: ToolDefinition[]) {
  return tools.map((t) => ({
    type: 'function' as const,
    function: {
      name: t.name,
      description: t.description,
      parameters: t.input_schema,
    },
  }))
}
