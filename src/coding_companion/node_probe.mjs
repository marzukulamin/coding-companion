// Run an explicitly approved installed CLI in its package directory, without a shell.
import { statSync } from 'node:fs';
import { isAbsolute } from 'node:path';
import { pathToFileURL } from 'node:url';

const [directory, cli, ...args] = process.argv.slice(2);
if (!directory || !cli || !isAbsolute(directory) || !isAbsolute(cli)
    || !statSync(directory).isDirectory() || !statSync(cli).isFile()) {
  throw new Error('An existing absolute package directory and CLI file are required');
}
process.chdir(directory);
process.argv = [process.execPath, cli, ...args];
await import(pathToFileURL(cli).href);
