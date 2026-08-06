import Wrapper from '../assets/wrappers/SafetyNotice';
import {LIMITATIONS_URL} from '../util/project';

// Every number in this notice is measured and is in README.md. "Roughly a third
// of falls" is the `fall` row's **missed as background** figure, 0.35 -- not its
// mAP@0.5 of 0.589, which sits in the neighbouring column and is not a miss rate.
// The gesture claim is the replay of 986 frames of a real worksite that emitted
// zero ARMS_UP and zero FRONT_BEND. If those measurements change, change this
// text with them -- the point of stating them here is that a visitor learns what
// the system misses before deciding what to rely on it for.
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
