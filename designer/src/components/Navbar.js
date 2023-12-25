import Wrapper from '../assets/wrappers/Navbar'
import {FaAlignLeft, FaCaretDown, FaUserCircle} from "react-icons/fa";
import {useDispatch, useSelector} from "react-redux";
import {Logo} from "./index";
import {logoutUser, toggleSidebar} from "../features/user/userSlice";
import {useState} from "react";

const Navbar = () => {
    const [showLogout, setShowLogout] = useState(false)
    const {user} = useSelector((store) => store.user)
    const dispatch = useDispatch();

    const toggle = () => {
        dispatch(toggleSidebar());
    };

    return (
        <Wrapper>
            <div className={'nav-center'}>
                <button type={'button'}
                        className={'toggle-btn'}
                        onClick={toggle}>
                    <FaAlignLeft/>
                </button>
                <div>
                    <Logo/>
                </div>
                <div className={'btn-container'}>
                    <button type={'button'}
                            className={'btn'}
                            onClick={() => setShowLogout(!showLogout)}>
                        <FaUserCircle/>
                        {user?.name}
                        <FaCaretDown/>
                    </button>
                    <div className={showLogout ? 'dropdown show-dropdown' : 'dropdown'}>
                        <button
                            onClick={() => {dispatch(logoutUser());}}
                            className='dropdown-btn'>
                            logout
                        </button>
                    </div>
                </div>
            </div>
        </Wrapper>
    )
}
export default Navbar;