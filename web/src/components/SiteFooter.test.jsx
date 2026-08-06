import {describe, expect, it} from 'vitest';
import {render, screen} from '@testing-library/react';

import SiteFooter from './SiteFooter';
import pkg from '../../package.json';

// The footer exists to satisfy AGPL section 13: a deployer running a modified
// copy over a network owes its users that copy's source, and this line is where
// those users find it. Its whole value is being present and correct, so the
// three things it has to carry are pinned rather than left to a code review.
describe('SiteFooter', () => {
    it('links to the source repository', () => {
        render(<SiteFooter/>);

        const link = screen.getByRole('link', {name: /source code/i});
        expect(link).toHaveAttribute(
            'href',
            'https://github.com/worksite-safety/worksite-safety-monitor'
        );
    });

    it('names the licence', () => {
        render(<SiteFooter/>);

        // Spelt exactly as the SPDX identifier in package.json and LICENSE.
        expect(screen.getByText(/AGPL-3\.0-or-later/)).toBeInTheDocument();
    });

    it('states the running version, read from package.json', () => {
        render(<SiteFooter/>);

        // Section 13 is about the source of *this* build, so the version is
        // taken from the manifest rather than typed into the component: a
        // release bump cannot leave the footer advertising an older tree.
        expect(screen.getByText(new RegExp(`v${pkg.version.replace(/\./g, '\\.')}`)))
            .toBeInTheDocument();
    });
});
