import Wrapper from '../assets/wrappers/SiteFooter';
import {APP_LICENSE, APP_NAME, APP_VERSION, SOURCE_URL} from '../util/project';

// AGPL section 13: anyone who runs a modified copy of this program and lets
// users reach it over a network owes those users the source of that copy.
// README.md describes the obligation; this line is the mechanism that lets a
// deployer discharge it, so it renders on every route -- the landing and login
// screens included, because an unauthenticated visitor is a user for section 13
// exactly as much as a logged-in one is.
const SiteFooter = () => {
    return (
        <Wrapper>
            <span>
                {APP_NAME} v{APP_VERSION}
            </span>
            <span className='sep' aria-hidden='true'>·</span>
            <span>Licensed {APP_LICENSE}</span>
            <span className='sep' aria-hidden='true'>·</span>
            <a href={SOURCE_URL} target='_blank' rel='noreferrer'>
                Source code
            </a>
        </Wrapper>
    );
};

export default SiteFooter;
