import {useState, useEffect} from 'react';
import {FormRow} from '../components';
import Wrapper from '../assets/wrappers/RegisterPage';
import {toast} from "react-toastify";
import {useDispatch, useSelector} from "react-redux";
import {forgotPassword, loginUser, registerUser} from "../features/user/userSlice";
import {useNavigate} from "react-router";
import "react-datepicker/dist/react-datepicker.css";

const initialState = {
    email: ''
};

function ForgotPassword() {
    const [values, setValues] = useState(initialState);

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
            email
        } = values;
        if (!email) {
            toast.error('Please fill out all fields')
            return;
        }

        dispatch(forgotPassword({
            email
        }))
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
                <h3>Forgot Password</h3>
                <FormRow type={'email'}
                         labelText={"Email"}
                         name={'email'}
                         value={values.email}
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

export default ForgotPassword;