import Wrapper from '../assets/wrappers/SafetyNotice';
import {LIMITATIONS_URL} from '../util/project';

// Every number in this notice is measured and is in README.md: fall detection
// scores mAP@0.5 = 0.589 on the validation split, and replaying 986 frames of a
// real worksite emitted zero ARMS_UP and zero FRONT_BEND. If those measurements
// change, change this text with them -- the point of stating them here is that a
// visitor learns what the system misses before deciding what to rely on it for.
const SafetyNotice = () => {
    return (
        <Wrapper role='note' aria-labelledby='safety-notice-title'>
            <h2 id='safety-notice-title'>This is not a certified safety system.</h2>
            <p>
                It does not replace human supervision, and it should never be the only thing
                watching a worksite. What it misses is measured, not guessed: on the validation
                split the model misses roughly a third of falls, and the two gesture detectors
                have never once fired on real footage. The full list is in the{' '}
                <a href={LIMITATIONS_URL} target='_blank' rel='noreferrer'>
                    project's known limitations
                </a>.
            </p>
        </Wrapper>
    );
};

export default SafetyNotice;
