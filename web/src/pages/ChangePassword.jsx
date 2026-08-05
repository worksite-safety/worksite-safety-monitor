import {useState, useEffect} from 'react';
import {FormRow} from '../components';
import Wrapper from '../assets/wrappers/RegisterPage';
import {toast} from "react-toastify";
import {useDispatch, useSelector} from "react-redux";
import {changePassword} from "../features/user/userSlice";
import {useLocation, useNavigate} from "react-router-dom";

const initialState = {
    password: '',
    confirmPassword: '',
    secretKey: ''
};

function ChangePassword() {
    const query = new URLSearchParams(useLocation().search);

    // The engine now percent-encodes the reset token when it builds the link
    // (MailService: URLEncoder.encode(...)), so URLSearchParams hands back the
    // exact Base64 string. The old `.replace(/ /g, '+')` patched a `+` that had
    // been decoded to a space by an unencoded link; it is a no-op today, and it
    // threw a TypeError when the page was opened without a ?token= at all.
    const [values, setValues] = useState(
        {...initialState, secretKey: query.get("token") ?? ''});

    const dispatch = useDispatch();
    const {isLoading, user} = useSelector((store) => store.user);

    const navigate = useNavigate();

    const handleChange = (e) => {
        const name = e.target.name;
        let value = e.target.value;

        setValues({...values, [name]: value});
    };

    const onSubmit = (e) => {
        e.preventDefault();

        const {
            password,
            confirmPassword,
            secretKey
        } = values;
        if (!password || !confirmPassword) {
            toast.error('Please fill out all fields')
            return;
        }
        if (password !== confirmPassword) {
            toast.error('Passwords does not match')
            return;
        }
        dispatch(changePassword({ password, confirmPassword, secretKey }));
        navigate("/register")

    };

    const toggleMember = () => {
        navigate("/landing")
    }

    useEffect(() => {
        if (user) {
            setTimeout(() => {
                navigate('/')
            }, 2000)
        }
    }, [user])


    return (
        <Wrapper className='full-page'>
            <form className='form' onSubmit={onSubmit}>
                <h3>Change Password</h3>
                <FormRow type={'password'}
                         labelText={"Password"}
                         name={'password'}
                         value={values.password}
                         handleChange={handleChange}/>
                <FormRow type={'password'}
                         labelText={"Confirm Password"}
                         name={'confirmPassword'}
                         value={values.confirmPassword}
                         handleChange={handleChange}/>

                {!values.isMember &&
                    <button type='submit' className='btn btn-block' disabled={isLoading}>
                        {isLoading ? 'loading...' : 'submit'}
                    </button>
                }
                {values.isMember &&
                    <button type='submit' className='btn btn-block' disabled={isLoading}>
                        {isLoading ? 'loading...' : 'submit'}
                    </button>

                }
                <p>
                    <button className={'member-btn'}
                            type={'button'}
                            onClick={toggleMember}

                    > Landing Page
                    </button>
                </p>
            </form>
        </Wrapper>
    );
}

export default ChangePassword;