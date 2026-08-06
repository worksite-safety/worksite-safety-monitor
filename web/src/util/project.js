// Identity of this build, in one place, because two separate obligations read
// it: AGPL section 13 wants the running version to point users at its own
// source, and the safety notice wants to be the same sentence everywhere.
//
// The version is imported from package.json rather than hard-coded so a release
// bump cannot leave the footer claiming an older build. Vite's JSON plugin emits
// named exports, so this pulls in the version string and tree-shakes the rest of
// the manifest out of the bundle.
import {version} from '../../package.json';

export const APP_NAME = 'Worksite AI Guardian';
export const APP_VERSION = version;
export const APP_LICENSE = 'AGPL-3.0-or-later';
export const SOURCE_URL = 'https://github.com/worksite-safety/worksite-safety-monitor';
export const LIMITATIONS_URL = `${SOURCE_URL}#known-limitations`;
