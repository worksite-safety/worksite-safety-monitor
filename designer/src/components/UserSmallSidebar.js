import Wrapper from '../assets/wrappers/SmallSidebar';
import { FaTimes } from 'react-icons/fa';
import Logo from './Logo';
import { useSelector, useDispatch } from 'react-redux';
import { toggleSidebar } from '../features/user/userSlice';
import UserNavLinks from './UserNavLinks';
const UserSmallSidebar = () => {
    const { isSidebarOpen } = useSelector((store) => store.user);
    const dispatch = useDispatch();

    const toggle = () => {
        dispatch(toggleSidebar());
    };
    return (
        <Wrapper>
            <div
                className={
                    isSidebarOpen ? 'sidebar-container show-sidebar' : 'sidebar-container'
                }
            >
                <div className='content'>
                    <button className='close-btn' onClick={toggle}>
                        <FaTimes />
                    </button>
                    <header>
                        <Logo />
                    </header>
                    <UserNavLinks toggleSidebar={toggle} />
                </div>
            </div>
        </Wrapper>
    );
};
export default UserSmallSidebar;