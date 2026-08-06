import {describe, expect, it} from 'vitest';
import {render, screen} from '@testing-library/react';

import SafetyNotice from './SafetyNotice';

// Before this component existed, a search of the whole repository for
// "not a substitute|not certified|life.safety|no warranty|disclaim" returned
// nothing outside a third-party licence file, while the landing page promised
// to protect lives. These cases pin the two sentences that reversed that, so a
// later tidy-up of the copy cannot quietly drop them.
describe('SafetyNotice', () => {
    it('says the system is not certified', () => {
        render(<SafetyNotice/>);

        expect(screen.getByText(/not a certified safety system/i)).toBeInTheDocument();
    });

    it('says it does not replace human supervision', () => {
        render(<SafetyNotice/>);

        expect(screen.getByText(/does not replace human supervision/i)).toBeInTheDocument();
    });

    it('points at the measured limitations rather than only asserting them', () => {
        render(<SafetyNotice/>);

        const link = screen.getByRole('link', {name: /known limitations/i});
        expect(link).toHaveAttribute(
            'href',
            'https://github.com/worksite-safety/worksite-safety-monitor#known-limitations'
        );
    });
});
