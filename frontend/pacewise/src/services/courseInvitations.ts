export const parseInvitationEmails = (value: string) => [...new Set(value.split(/[\s,;]+/).map(email => email.trim().toLowerCase()).filter(Boolean))];
