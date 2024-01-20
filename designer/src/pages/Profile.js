import React, { useEffect, useState } from "react";
import { FormRow } from "../components";
import Wrapper from "../assets/wrappers/ProfilePage";
import { useDispatch, useSelector } from "react-redux";
import { toast } from "react-toastify";
import { updateUser } from "../features/user/userSlice";
import BadgeOutlinedIcon from "@mui/icons-material/BadgeOutlined";
import "./profile.css";
import { EmailOutlined, BadgeOutlined, AbcOutlined } from "@mui/icons-material";

const Profile = () => {
  const { isLoading, user } = useSelector((store) => store.user);
  const dispatch = useDispatch();

  const [userUpdateData, setUserUpdateDataData] = useState({
    newPassword: "",
    newPasswordConfirm: "",
  });
  const [userData, setUserData] = useState({
    id: user?.id || "",
    lastName: user?.lastName || "",
    name: user?.name || "",
    role: user?.role || "",

    email: user?.email || "",
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    const { newPassword, newPasswordConfirm } = userUpdateData;

    if (!newPassword || !newPasswordConfirm) {
      toast.error("Please Fill Out All Fields");
      return;
    }
    if (newPassword !== newPasswordConfirm) {
      toast.error("Passwords Do Not Match");
      return;
    }
    dispatch(updateUser(userUpdateData));
  };
  const handleChange = (e) => {
    const name = e.target.name;
    const value = e.target.value;

    setUserUpdateDataData((prevState) => ({ ...prevState, [name]: value }));
  };

  useEffect(() => {});

  return (
      <Wrapper className="profile-wrapper">
        <div className="user-info">
          <h2>User Information</h2>
          <div className="user-details">
            <h3>
              <BadgeOutlined /> {userData.name} {userData.lastName}
            </h3>
            <h4 className="user-email">
              <EmailOutlined /> {userData.email}
            </h4>
          </div>
        </div>

        <form className="user-profile-form" onSubmit={handleSubmit}>
          <div className="form-container">
            <div className="change-password-section">
              <h2>Change Password</h2>
              <div className="password-fields">
                <div className="input-w-label">
                  <label>New Password:</label>
                  <input
                      type="password"
                      name="newPassword"
                      value={userUpdateData.newPassword}
                      onChange={handleChange}
                      className="password-input"
                  />
                </div>
                <div className="input-w-label">
                  <label>Confirm Password:</label>
                  <input
                      type="password"
                      name="newPasswordConfirm"
                      value={userUpdateData.newPasswordConfirm}
                      onChange={handleChange}
                      className="password-input"
                  />
                </div>

                <button className="submit-btn" type="submit" disabled={isLoading}>
                  {isLoading ? "Please Wait..." : "Update Information"}
                </button>
              </div>
            </div>
          </div>
        </form>
      </Wrapper>
  );
};

export default Profile;
