import "./App.css";

// react-router-dom was discontinued at v8; its whole surface -- including the
// DOM-only BrowserRouter/Link/NavLink -- now ships from `react-router` itself.
import {BrowserRouter, Route, Routes} from "react-router";
import 'react-toastify/dist/ReactToastify.css'
import {ToastContainer} from "react-toastify";
import {
    Landing,
    Error,
    Register,
    UserSharedLayout,
    Profile,
    Video,
    Reporting,
    ChangePassword,
    ForgotPassword,
    UserProtectedRoute,
    ChartsContainer

} from "./pages"
import {SiteFooter} from "./components";
import {useSelector} from "react-redux";

// react-toastify 11 binds Alt+T on `document` to focus the toast region. v9 had
// no such shortcut, and `hotKeys` is the documented predicate that gates it, so
// a matcher that never matches turns it back off. Hoisted to module scope
// because the container re-registers its keydown listener whenever this
// function's identity changes.
const NO_TOAST_HOTKEY = () => false;

function App() {



    const {user} = useSelector((store) => store.user);
    return (

        <BrowserRouter>

            <Routes>

                {user && user.role === 'ADMIN' && <Route
                    path='/'
                    element={
                        <UserProtectedRoute>
                            <UserSharedLayout/>
                        </UserProtectedRoute>
                    }
                >
                    <Route index element={<ChartsContainer/>}/>
                    <Route path='statistics' element={<ChartsContainer/>}/>
                    <Route path='video' element={<Video/>}/>
                    <Route path='reports' element={<Reporting/>}/>
                    <Route path='profile' element={<Profile/>}/>


                </Route>}
                <Route path='/' element={<Landing/>}/>
                <Route path='landing' element={<Landing/>}/>
                <Route path='register' element={<Register/>}/>
                <Route path='forgot-password' element={<ForgotPassword/>}/>
                <Route path='change-password' element={<ChangePassword/>}/>
                <Route path='*' element={<Error/>}/>
            </Routes>
            {/* Outside <Routes> so the AGPL section 13 source offer is on every
                screen, authenticated or not, without each page remembering to
                render it. */}
            <SiteFooter/>
            {/* draggable: v11 changed the default from true to 'touch', which
                dropped mouse-drag dismissal. true restores the v9 gesture for
                both pointer types. aria-label: v11's default is the literal
                string "Notifications Alt+T", which would advertise the shortcut
                disabled just above. */}
            <ToastContainer position='top-center'
                            draggable={true}
                            hotKeys={NO_TOAST_HOTKEY}
                            aria-label='Notifications'/>
        </BrowserRouter>
    )
        ;

}

export default App;