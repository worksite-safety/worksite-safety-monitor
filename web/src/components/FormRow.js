import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';

const FormRow = ({type, name, value, handleChange, labelText}) => {
    if (type === 'date') {
        const maxDate = new Date();
        maxDate.setFullYear(maxDate.getFullYear() - 18); // Set max date to 18 years ago
        const minDate = new Date();
        minDate.setFullYear(minDate.getFullYear() - 80); // Set min date to 80 years ago

        return (
            <div className='form-row'>
                <label htmlFor={name} className='form-label'>
                    {labelText || name}
                </label>
                <DatePicker
                    selected={value}
                    onChange={(date) => handleChange({target: {name, value: date}})}
                    maxDate={maxDate}
                    minDate={minDate}
                    className='form-input'
                    dateFormat="MM/dd/yyyy"
                    placeholderText="MM/DD/YYYY"
                />
            </div>
        );
    }

    return (
        <div className='form-row'>
            <label htmlFor={name} className='form-label'>
                {labelText || name}
            </label>
            <input
                type={type}
                value={value}
                name={name}
                onChange={handleChange}
                className='form-input'
                placeholder={
                    name === 'search' ? 'Brand Name' :
                    name === 'email' ? 'aiproject@aiproject.com' :
                    name === 'gpa' ? '2.45' :
                    name === 'identityNumber' ? '36818766449' :
                        name === 'phoneNumber' ? '05343943539' : ''
                }
            />
        </div>
    );
};

export default FormRow;
