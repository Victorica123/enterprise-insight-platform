package com.example.videoplatform.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;

import com.example.videoplatform.config.AppProperties;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.server.ResponseStatusException;

class OidcWorkspaceExchangeTests {
    private final UserAccountRepository users = mock(UserAccountRepository.class);
    private final WorkspaceService workspaces = mock(WorkspaceService.class);
    private final OidcIdentityVerifier verifier = mock(OidcIdentityVerifier.class);
    private final JwtService jwt = mock(JwtService.class);
    private final AuthService service = new AuthService(users, mock(PasswordEncoder.class), jwt,
            mock(LoginRateLimiter.class), new AppProperties(), workspaces, verifier);

    @BeforeEach
    void identity() {
        var user = UserAccount.oidc("user", "name", "issuer", "subject");
        when(verifier.verify("external")).thenReturn(
                new OidcIdentityVerifier.ExternalIdentity("issuer", "subject", "name"));
        when(users.findByIdentityIssuerAndIdentitySubject("issuer", "subject")).thenReturn(Optional.of(user));
        when(workspaces.ensurePersonalWorkspace(user)).thenReturn(
                new WorkspaceService.WorkspaceContext("personal", "admin", "personal"));
        when(jwt.generateAccessToken(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn("signed");
    }

    @Test
    void refreshReReadsMembershipAndSignsDowngradedRole() {
        when(workspaces.requireContext("user", "team")).thenReturn(
                new WorkspaceService.WorkspaceContext("team", "viewer", "team"));
        var response = service.loginOidc("external", "team");
        assertThat(response.tenantId()).isEqualTo("team");
        assertThat(response.role()).isEqualTo("viewer");
        verify(jwt).generateAccessToken("user", "name", "team", "viewer", "team");
    }

    @Test
    void unknownOrRevokedMembershipNeverSignsRequestedTenant() {
        when(workspaces.requireContext("user", "other")).thenThrow(
                new ResponseStatusException(HttpStatus.NOT_FOUND, "工作区不存在"));
        assertThatThrownBy(() -> service.loginOidc("external", "other"))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(error -> assertThat(((ResponseStatusException) error).getStatusCode())
                        .isEqualTo(HttpStatus.NOT_FOUND));
        verifyNoInteractions(jwt);
    }

    @Test
    void exchangeWithoutRequestedTenantUsesPersonalMembership() {
        var response = service.loginOidc("external");
        assertThat(response.tenantId()).isEqualTo("personal");
        verify(workspaces, never()).requireContext(anyString(), anyString());
    }

    @Test
    void invalidExternalIdentityCannotReachWorkspaceOrSigning() {
        when(verifier.verify("invalid")).thenThrow(new ResponseStatusException(HttpStatus.UNAUTHORIZED));
        assertThatThrownBy(() -> service.loginOidc("invalid", "team"))
                .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(workspaces, jwt);
    }
}
