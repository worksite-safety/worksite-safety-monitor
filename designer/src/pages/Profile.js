import React, {useEffect, useState} from 'react';
import {FormRow} from '../components';
import Wrapper from '../assets/wrappers/ProfilePage';
import {useDispatch, useSelector} from 'react-redux';
import {toast} from 'react-toastify';
import {updateUser} from '../features/user/userSlice';
import BadgeOutlinedIcon from '@mui/icons-material/BadgeOutlined';
import {
  EmailOutlined, BadgeOutlined, AbcOutlined
} from "@mui/icons-material";

const Profile = () => {
  const {isLoading, user} = useSelector((store) => store.user);
  const dispatch = useDispatch();

  const [userUpdateData, setUserUpdateDataData] = useState({
    newPassword: '',
    newPasswordConfirm: '',
  })
  const [userData, setUserData] = useState({
    id: user?.id || '',
    lastName: user?.lastName || '',
    name: user?.name || '',
    role: user?.role || '',

    email: user?.email || ''
  })

  const handleSubmit = (e) => {
    e.preventDefault();
    const {newPassword, newPasswordConfirm} = userUpdateData;

    if (!newPassword || !newPasswordConfirm) {
      toast.error('Please Fill Out All Fields');
      return;
    }
    if (newPassword !== newPasswordConfirm) {
      toast.error('Passwords Do Not Match');
      return;
    }
    dispatch(updateUser(userUpdateData));
  };
  const handleChange = (e) => {
    const name = e.target.name;
    const value = e.target.value;

    setUserUpdateDataData(prevState => ({...prevState, [name]: value}));
  };

  useEffect(() => {

  });

  return (
      <Wrapper>
        <form className='form' onSubmit={handleSubmit}>
          <h3>User Information</h3>
          <div>
            <h4><BadgeOutlined/>User Name: {userData.name} {userData.lastName}
            </h4>
          </div>
          <div>
            <div>

              <div>
                <h4><EmailOutlined/> Email:{userData.email}</h4>
              </div>
            </div>
          </div>
          <div>
            <br/>
            <br/><br/><br/>
            <h3>Change Password </h3>
            <div>
              <FormRow
                  type='password'
                  name='newPassword'
                  labelText={"New Password"}
                  value={userUpdateData.newPassword}
                  handleChange={handleChange}
              />

              <FormRow
                  type='password'
                  labelText={"Confirm Password"}
                  name='newPasswordConfirm'
                  value={userUpdateData.newPasswordConfirm}
                  handleChange={handleChange}
              />
              <button className='btn btn-block' type='submit'
                      disabled={isLoading}>
                {isLoading ? 'Please Wait...'
                    : 'Update Information'}
              </button>
            </div>
          </div>
        </form>
      </Wrapper>
  );
};

export default Profile;
