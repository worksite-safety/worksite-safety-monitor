import {useState, useEffect} from 'react';
import {FormRow} from '../components';
import Wrapper from '../assets/wrappers/RegisterPage';
import {toast} from "react-toastify";
import {useDispatch, useSelector} from "react-redux";
import {loginUser, registerUser} from "../features/user/userSlice";
import {useNavigate} from "react-router-dom";
import "react-datepicker/dist/react-datepicker.css";

const initialState = {
    firstName: '',
    lastName: '',
    email: '',
    password: '',
    isMember: true
};

function Register() {
    const [values, setValues] = useState(initialState);

    const dispatch = useDispatch();
    const {isLoading, user} = useSelector((store) => store.user);

    const navigate = useNavigate();


    const handleChange = (e) => {
        const name = e.target.name;
        let value = e.target.type === 'date' ? new Date(e.target.value).toISOString() : e.target.value;

        if (name === 'identityNumber' || name === 'phoneNumber') {
            // Remove any non-digit characters from the value
            value = value.replace(/\D/g, '');

            const maxLength = name === 'identityNumber' ? 12 : 11;
            value = value.slice(0, maxLength);
        }
        console.log(`${name}: ${value}`);
        setValues({...values, [name]: value});
    };

    const onSubmit = (e) => {
        e.preventDefault();
        const {
            firstName,
            lastName,
            email,
            password,
            isMember
        } = values;
        if (!email || !password || (!isMember && (!firstName || !lastName))) {
            toast.error('Please fill out all fields')
            return;
        }

        if (isMember) {
            dispatch(loginUser({email: email, password: password}))
            return;
        }
        dispatch(registerUser({
            firstName,
            lastName,
            email,
            password
        }))
    };

    const toggleMember = () => {
        setValues({...values, isMember: !values.isMember})
    }
    const navigateToForgotPassword = () => {
        navigate("/forgot-password")
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

                <h3>{values.isMember ? 'Login' : 'Register'}</h3>

                {!values.isMember &&
                    <FormRow type={'text'}
                             labelText={"First Name"}
                             name={'firstName'}
                             value={values.firstName}
                             handleChange={handleChange}/>
                }
                {!values.isMember &&
                    <FormRow type={'text'}
                             labelText={"Last Name"}
                             name={'lastName'}
                             value={values.lastName}
                             handleChange={handleChange}/>
                }
                <FormRow type={'email'}
                         labelText={"Email"}
                         name={'email'}
                         value={values.email}
                         handleChange={handleChange}/>
                <FormRow type={'password'}
                         labelText={"Password"}
                         name={'password'}
                         value={values.password}
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
                    {values.isMember ? 'You are not member?' : 'If you are member?'}

                    <button className={'member-btn'}
                            type={'button'}
                            onClick={toggleMember}

                    >{values.isMember ? 'Register' : 'Login'}

                    </button>
                </p>
                {values.isMember && <p>
                    <button className={'member-btn'}
                            type={'button'}
                            onClick={navigateToForgotPassword}
                    > Forgot password
                    </button>
                </p>
                }
            </form>
        </Wrapper>
    );
}

export default Register;